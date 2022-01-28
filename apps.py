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
    FCOL_LENGTH = '{: <40}'
    RCOL_LENGTH = '{: >20}'

    @staticmethod
    def print_progress(name, i, length, color=''):
        unit = int(length / 50)
        cur = '#' * int(i / unit)
        remain = ' ' * int((length - i) / unit)
        progress = i / length * 100
        s = STD.FCOL_LENGTH.format(name)
        s += '{: >50}'.format(f"[{cur}{remain}] {'%2.0f' % progress}%")
        print(f"\r{color}{s}", end=" ")

    @staticmethod
    def print(*args, color=None, same_line=False):
        args = [str(e) for e in args]
        first = args.pop(0)
        s = f"{STD.RESET}"
        if color:
            s += color
        s += STD.FCOL_LENGTH.format(first)
        s += (STD.RCOL_LENGTH * len(args)).format(*args)
        if same_line:
            print(f"\r{s}", end=' ', flush=True)
        else:
            print(s, flush=True)


class AppTools():
    def _test_repo(self, repo, repos):
        ret = requests.get(f"{WEB}/{repo}/releases/latest")
        tag = ret.url.split("/")[-1]
        if ret and ".appimage" in ret.text.lower():
            repos.append((repo, tag))

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
        STD.print(repo, "Downloading ...", color=STD.INFO)
        file = requests.get(self._apps[repo]["latest"]["url"], stream=True)
        length = int(float(file.headers["content-length"]))
        with open(self._apps[repo]["path"], "wb") as application:
            i = 0
            for chunk in file.iter_content(chunk_size=chunk_size):
                if chunk:
                    i += chunk_size
                    application.write(chunk)
                    STD.print_progress(repo, i, length, color=STD.INFO)
        STD.print("")
        STD.print(repo, "Application updated", color=STD.SUCCESS)
        os.chmod(self._apps[repo]["path"], 0o755)
        self._apps[repo]["current"]["url"] = self._apps[repo]["latest"]["url"]
        self._apps[repo]["current"]["tag"] = self._apps[repo]["latest"]["tag"]
        self._load_state(repo)
        self._save()

    def _search(self, keywords):
        ret = requests.get(
            f"{API}/search/repositories?q={keywords} in:name&page_size=100")
        repos = []
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


class AppManager(AppTools):

    def __init__(self):
        if not os.path.exists(APPDIR):
            os.mkdir(APPDIR)
        self._load()
        self._install_appimaged()

    def search(self, keywords=[]):
        """
        Search for an application by name
        """
        repos = self._search(' '.join(keywords))
        repos += self._search(f"{' '.join(keywords)} appimage")
        
        if len(repos) > 0:
            STD.print("REPO NAME", "VERSION", "ID", color=STD.INFO)
            STD.print("---------", "-------", "--", color=STD.INFO)
            for id, (name, tag) in enumerate(repos):
                if name in self._apps.keys():
                    if self._apps[name]["current"]["tag"] != tag:
                        STD.print(name, tag, "OutDated", color=STD.WARNING)
                    else:
                        STD.print(name, tag, "Installed", color=STD.SUCCESS)
                else:
                    STD.print(name, tag, id, color=STD.INFO)
            STD.print("", "", "", color=STD.INFO)
            try:
                install = int(
                    float(input(f"{STD.INFO}Please enter ID to install ( -1 for None ) ? : ") or -1))
                if install < 0 or install > len(repos):
                    return
                else:
                    repo, tag = repos[install]
                    self.install(repo)
                    return
            except:
                return
        else:
            STD.print("Sorry, there are no repos found", color=STD.ERROR)

    def install(self, repo=[]):
        """
        Install an application from Github repository name
        """
        if type(repo) is list:
            for r in repo:
                self.install(r)
        elif type(repo) is str:
            if repo in self._apps.keys():
                STD.print(repo, "App already exists", color=STD.ERROR)
            else:
                self._add_app(repo)
                self.check(repo)
                self.update(repo)

    def remove(self, repo=[]):
        """
        Remove an application
        """
        if type(repo) is list:
            for r in repo:
                self.remove(r)
        elif type(repo) is str:
            if repo in self._apps.keys():
                if os.path.exists(self._apps[repo]["path"]):
                    os.unlink(self._apps[repo]["path"])
                del self._apps[repo]
                self._save()
            else:
                STD.print(repo, "App not found", color=STD.ERROR)

    def update(self, repo=[]):
        """
        Update an application, if not specified, all applications will be updated
        """
        if type(repo) is list:
            repo = repo if len(repo) > 0 else self._apps.keys()
            for r in repo:
                self.update(r)
            STD.print("", "")
        elif type(repo) is str:
            if repo in self._apps.keys():
                if self._apps[repo]["state"]["need_update"]:
                    self._download(repo)
                else:
                    STD.print(repo, "UpToDate", color=STD.SUCCESS)
            else:
                STD.print(repo, "NotFound", color=STD.ERROR)

    def check(self, repo=[]):
        """
        Check if newer version is available for an application, if not specified, all applications will be checked
        """
        if type(repo) is list:
            repo = repo if len(repo) > 0 else self._apps.keys()
            for r in repo:
                self.check(r)
        elif type(repo) is str:
            latest_url, latest_tag = self._get_latest_version(repo)
            self._apps[repo]["latest"] = {
                "url": latest_url,
                "tag": latest_tag
            }
            self._load_state(repo)
            if self._apps[repo]["state"]["need_update"]:
                STD.print(repo, "New version available !",
                          self._apps[repo]["latest"]["tag"], color=STD.WARNING)
            else:
                STD.print(repo, "UpToDate",
                          self._apps[repo]["latest"]["tag"], color=STD.SUCCESS)
        self._save()

    def list(self):
        """
        List installed applications
        """
        STD.print("REPO NAME", "INSTALLED", "NEED UPDATE",
                  "CURRENT", "LATEST", color=STD.INFO)
        STD.print("---------", "---------", "-----------",
                  "-------", "------", color=STD.INFO)
        for repo, meta in self._apps.items():
            color = STD.INFO
            if not meta["state"]["installed"]:
                color = STD.ERROR
            elif meta["state"]["need_update"]:
                color = STD.WARNING
            STD.print(repo, meta["state"]["installed"], meta["state"]["need_update"],
                      meta["current"]["tag"], meta["latest"]["tag"], color=color)


fire.Fire(AppManager())
