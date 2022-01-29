import os
import re
from threading import Thread

import fire
import requests
import yaml

APPDIR = f"{os.getenv('HOME')}/Applications"
WEB = "https://github.com"
API = "https://api.github.com"
APPIMAGED = "probonopd/go-appimage"


class STD:
    ERROR = "\033[1;31m"
    INFO = "\033[1;36m"
    SUCCESS = "\033[0;32m"
    RESET = "\033[0;0m"
    WARNING = '\033[33m'
    F_COL_LENGTH = '{: <40} %s│ %s'
    R_COL_LENGTH = '{: <30} %s│ %s'
    I_ERROR =  '⛔️'
    I_WARNING ='⚠️'
    I_SUCCESS = '✅️'
    I_INFO = '💡️'

    @staticmethod
    def print_progress(*args, i, length, color=''):
        unit = int(length / 22)
        cur = '#' * int(i / unit)
        remain = ' ' * int((length - i) / unit)
        progress = i / length * 100
        s = '{: >22}'.format(f"[{cur}{remain}] {'%2.0f' % progress}%")
        STD.print(*args, s, color=color, same_line=True)

    @staticmethod
    def print_separator(chr,chr_s, chr_e,chr_m, cols):
        s = f"{STD.RESET}"
        s += chr_s
        s += chr * 42
        s += chr_m
        for _ in range(cols-1):
            s += (chr * 32 + chr_m)
        s = s[:-1] + chr_e
        print(s, flush=True)

    @staticmethod
    def print(*args, color=None, same_line=False):
        if not color:
            color = STD.RESET
        args = [str(e) for e in args]
        first = args.pop(0)
        s = f"{STD.RESET}│ {color}"
        s += (STD.F_COL_LENGTH % (STD.RESET, color) ).format(first)
        s += (STD.R_COL_LENGTH % (STD.RESET, color) * len(args)).format(*args)
        if same_line:
            print(f"\r{s}", end=' ', flush=True)
        else:
            print(s, flush=True)
    @staticmethod
    def message(str_message, color=''):
        icon = STD.I_INFO
        if color == STD.ERROR:
            icon = STD.I_ERROR
        elif color == STD.WARNING:
            icon = STD.I_WARNING
        elif color == STD.SUCCESS:
            icon = STD.I_SUCCESS

        STD.print_separator('─','╭',icon, '┬', 1)
        str_message = '\n'.join(line.strip() for line in re.findall(r'.{1,40}(?:\s+|$)', str_message))
        for s in str_message.splitlines():
            STD.print(s, color=color)
        STD.print_separator('─','╰','╯','┴', 1)
    

class AppTools():
    def _test_repo(self, repo, repos):
        ret = requests.get(f"{WEB}/{repo}/releases/latest")
        tag = ret.url.split("/")[-1]
        if ret and ".appimage" in ret.text.lower():
            repos[repo] = tag

    def _install_appimaged(self):
        if APPIMAGED not in self._apps.keys():
            self.install(APPIMAGED)
            os.system(f'{self._apps[APPIMAGED]["path"]}')

    def _load(self):
        self._apps = {}
        if os.path.exists(f'{APPDIR}/list.yaml'):
            with open(f'{APPDIR}/list.yaml') as fp:
                apps = yaml.load(fp,  Loader=yaml.FullLoader)
                for repo, meta in apps.items():
                    self._add_app(repo, meta)

    def _save(self):
        with open(f'{APPDIR}/list.yaml', mode="w") as fp:
            yaml.dump(self._apps, fp, allow_unicode=True)

    def _load_state(self, repo):
        installed = os.path.exists(self._apps[repo]["path"])
        need_update = self._apps[repo]["latest"]["url"] and self._apps[repo]["current"]["url"] != self._apps[repo]["latest"]["url"]
        self._apps[repo]["state"] = {
            "need_update": need_update,
            "installed": installed
        }

    def _add_app(self, repo, meta={}):

        path = f'{APPDIR}/{"_".join(x for x in repo.split("/"))}.AppImage'
        if "path" in meta:
            path = meta["path"]
        current_tag = None
        current_url = None

        if "current" in meta:
            current_tag = meta["current"]["tag"]
            current_url = meta["current"]["url"]

        latest_tag = None
        latest_url = None

        if "latest" in meta:
            latest_tag = meta["latest"]["tag"]
            latest_url = meta["latest"]["url"]

        name = "_".join(x for x in repo.split("/"))
        if "name" in meta:
            name = meta["name"]

        self._apps[repo] = {
            "name": name,
            "path": path,
            "current": {
                "tag": current_tag,
                "url": current_url
            },
            "latest": {
                "tag": latest_tag,
                "url": latest_url
            }
        }
        self._load_state(repo)

    def _get_latest_version(self, repo):
        url = None
        tag = None
        ret = requests.get(f"{WEB}/{repo}/releases/latest")
        if ret:
            tag = ret.url.split("/")[-1]
            urls = [f"{WEB}{''.join(e)}" for e in re.findall(
                '"(/'+repo+'/)(\w+:{0,1}\w*@)?(\S+)(:[0-9]+)*(\.AppImage|\.appimage)"', ret.text.rstrip())]
            url = next((u for u in urls if not re.match(
                ".*(arm|i\d{3}|aarch|linux32).*", u)), None)
        return (url, tag)

    def _download(self, repo):
        chunk_size = 102400
        file = requests.get(self._apps[repo]["latest"]["url"], stream=True)
        length = int(float(file.headers["content-length"]))
        with open(self._apps[repo]["path"], "wb") as application:
            i = 0
            for chunk in file.iter_content(chunk_size=chunk_size):
                if chunk:
                    i += chunk_size
                    application.write(chunk)
                    STD.print_progress(repo,
                        "Installing",
                        self._apps[repo]["current"]["tag"],
                        i=i, length=length,
                        color=STD.WARNING
                        )
        os.chmod(self._apps[repo]["path"], 0o755)
        self._apps[repo]["current"]["url"] = self._apps[repo]["latest"]["url"]
        self._apps[repo]["current"]["tag"] = self._apps[repo]["latest"]["tag"]
        self._load_state(repo)
        self._print_status(repo, same_line=True)

    def _search(self, keywords):
        ret = requests.get(
            f"{API}/search/repositories?q={keywords} in:name&page_size=100")
        repos = {}
        if ret:
            d = ret.json()
            threads = []
            for e in d["items"]:
                t = Thread(target=self._test_repo,
                           args=(e["full_name"], repos))
                t.start()
                threads.append(t)
            for t in threads:
                t.join()
        return repos

    def _check(self, repo):
        latest_url, latest_tag = self._get_latest_version(repo)
        self._apps[repo]["latest"] = {
            "url": latest_url,
            "tag": latest_tag
        }
        self._load_state(repo)

    def _update(self, repo):
        if repo in self._apps.keys():
            if self._apps[repo]["state"]["need_update"]:
                self._download(repo)
            else:
                self._print_status(repo)
        else:
            self._print_status(repo)

    def _get_color_and_status(self, repo):
        if not self._apps[repo]["state"]["installed"]:
            color = STD.ERROR
            status = STD.I_ERROR+" Pending"
        elif self._apps[repo]["state"]["need_update"]:
            color = STD.WARNING
            status = STD.I_WARNING+" New version available !"
        else:
            color = STD.SUCCESS
            status = STD.I_SUCCESS+" Up to date"
        return (color, status)

    def _print_headers(self, labels=True):
        STD.print_separator('─','╭','╮','┬', 4)
        if labels:
            STD.print("APPLICATION", "STATUS",
                  "CURRENT", "LATEST", color=STD.INFO)
            STD.print_separator( '─','├','┤','┼', 4)

    def _print_status(self, repo, same_line=False):
        color, status = self._get_color_and_status(repo)
        STD.print(repo,
                 status,
                 self._apps[repo]["current"]["tag"],
                 self._apps[repo]["latest"]["tag"],
                color=color,
                same_line=same_line
                )
        if same_line:
            print()
    def _print_footer(self):
        STD.print_separator('─','╰','╯','┴', 4)

class AppManager(AppTools):
    """
    AppImage Package Manager 
    
    AppImage Package Manager is a simple tool written in python 
    that allows you to install AppImage applications retrieved from GitHub 
    and integrate them into your GNU/Linux system 
    
    see: https://github.com/probonopd/go-appimage

    Samir KHERRAZ
    https://www.equantum.fr
    https://github.com/samirkherraz/AppImagePackageManager
    """

    def __init__(self):
        if not os.path.exists(APPDIR):
            os.mkdir(APPDIR)
        self._load()
        self._install_appimaged()

    def search(self, keywords):
        """
        Search for an application by name
        """
        repos=self._search(keywords)
        repos.update(self._search(f"{keywords} appimage"))

        if len(repos) > 0:
            self._print_headers()
            for name, tag in repos.items():
                color = STD.RESET
                if name in self._apps.keys():
                    color, status = self._get_color_and_status(name)
                    STD.print(name,
                            status,
                            self._apps[name]["current"]["tag"],
                            self._apps[name]["latest"]["tag"],
                            color=color
                            )
                else:
                    STD.print(name,
                            STD.I_INFO+" Available",
                            '',
                            tag,
                            color=color
                            )
            self._print_footer()
            try:
                repo=input(f"{STD.INFO}{STD.I_INFO} Please enter repos name to install ? : ")
                if not repo:
                    return 
                if repo in repos:
                    self._print_headers(False)
                    self._add_app(repo)
                    self._check(repo)
                    self._update(repo)
                    self._print_footer()
                else:
                    STD.message(f"Sorry, but {repo} is not present in application list",color=STD.ERROR)

            except:
                pass
        else:
            STD.message(f"Sorry, there are no repos found for {keywords}", color=STD.ERROR)

    def install(self, repo):
        """
        Install an application from Github repository name
        """
        repos = self._search(repo)
        if repo in repos:
            self._print_headers()
            self._add_app(repo)
            self._check(repo)
            self._update(repo)
            self._print_footer()
        else:
            STD.message("Sorry, but {repo} couldn't be found", color=STD.ERROR)

    def remove(self, repo):
        """
        Remove an application
        """
        if repo not in self._apps:
            STD.message(f"Sorry, {repo} is not found in installed applications", color=STD.ERROR)
            return

        if repo in self._apps.keys():
            if os.path.exists(self._apps[repo]["path"]):
                os.unlink(self._apps[repo]["path"])
            del self._apps[repo]
            STD.message(f"Application {repo} successfully removed", color=STD.SUCCESS)

        else:
            STD.message(f"Application {repo} is not found", color=STD.ERROR)

    def update(self, repo):
        """
        Update an application, if not specified, all applications will be updated
        """
        if repo not in self._apps:
            STD.message(f"Sorry, {repo} is not found in installed applications", color=STD.ERROR)
            return
        self._print_headers()
        self._update(repo)
        self._print_footer()

    def check(self, repo):
        """
        Check if newer version is available for an application, if not specified, all applications will be checked
        """
        if repo not in self._apps:
            STD.message(f"Sorry, {repo} is not found in installed applications", color=STD.ERROR)
            return
        self._print_headers()
        self._check(repo)
        self._print_status(repo)
        self._print_footer()


    def update_all(self):
        """
        Update all applications
        """
        self._print_headers()
        for repo in self._apps:
            self._update(repo)
        self._print_footer()

    def auto(self):
        """
        Check for newer versions and update all applications
        """
        self._print_headers()
        for repo in self._apps:
            self._check(repo)
            self._update(repo)
        self._print_footer()

    def list(self):
        """
        List installed applications
        """
        self._print_headers()
        for repo in self._apps:
            self._print_status(repo)
        self._print_footer()
app_manager = AppManager()
fire.Fire(app_manager)
app_manager._save()
