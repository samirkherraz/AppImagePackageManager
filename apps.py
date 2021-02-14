import requests
import re
import os
from threading import Thread
import sys
import yaml



APPDIR = f"{os.getenv('HOME')}/Applications"
WEB = "https://github.com"
API = "https://api.github.com"
APPIMAGED = "probonopd/go-appimage"

class STD:
    ERROR   = "\033[1;31m"  
    INFO  = "\033[1;36m"
    SUCCESS = "\033[0;32m"
    RESET = "\033[0;0m"
    WARNING = '\033[33m' 
    FCOL_LENGTH='{: <40}'
    RCOL_LENGTH='{: >20}'

    @staticmethod
    def print_progress(name, i, length, color=''):
        unit = int(length / 50)
        cur = '#' * int(i / unit)
        remain = ' ' * int((length - i) / unit)
        progress = i / length * 100
        lst = [name, ]
        s = STD.FCOL_LENGTH.format(name)
        s += '{: >50}'.format(f"[{cur}{remain}] {'%2.0f' % progress}%")
        print(f"\r{color}{s}", end=" ")
    
    @staticmethod
    def print(*args, color=None,same_line=False):
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


class AppSearch():
    def test_repo(self, repo, repos):
        url = None
        ret = requests.get(f"{WEB}/{repo}/releases/latest")
        tag = ret.url.split("/")[-1]
        if ret and ".appimage" in ret.text.lower():
            repos.append((repo,tag))
            
    def search(self, keywords=[]):
        ret = requests.get(f"{API}/search/repositories?q={' '.join(keywords)} in:name&page_size=100")
        if ret:
            d = ret.json()
            threads = []
            repos = []
            for e in d["items"]:
                STD.print("Testing",e["full_name"], "", color=STD.INFO, same_line=True)
                t = Thread(target=self.test_repo, args=(e["full_name"], repos))
                t.start()
                threads.append(t)
            STD.print("", "","", color=STD.INFO, same_line=True)
            for t in threads:
                t.join()
            STD.print("")
            STD.print("REPO NAME","VERSION", "ID", color=STD.INFO)
            STD.print("---------","-------", "--", color=STD.INFO)
            for i in range(len(repos)):
                name, tag = repos[i]
                if name in self.apps.keys():
                    if self.apps[name]["current"]["tag"] != tag:
                        STD.print(name,tag, "OutDated", color=STD.WARNING)
                    else:
                        STD.print(name,tag, "Installed", color=STD.SUCCESS)

                else:
                    STD.print(name,tag, i, color=STD.INFO)

            if len(repos) > 0:
                STD.print("", "", "", color=STD.INFO)
                install = int(float(input(f"{STD.INFO}Please enter ID to install ( -1 for None ) ? : ")))
                if install < 0 or install > len(repos):
                    return False
                else:
                    repo, tag = repos[install]
                    self.install(repo)
                    return True
            else:
                STD.print("Sorry, there are no repos found", color=STD.ERROR)



class AppState():
    

    def load_state(self,repo):
        installed = os.path.exists(self.apps[repo]["path"])
        need_update =  self.apps[repo]["latest"]["url"] and self.apps[repo]["current"]["url"] != self.apps[repo]["latest"]["url"]
        self.apps[repo]["state"] = {
            "need_update": need_update,
            "installed": installed
        }

    def add_app(self, repo, meta={}):
        
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

        self.apps[repo] = {
            "name": name,
            "path": path,
            "current":{
                "tag": current_tag,
                "url": current_url
            },
            "latest":{
                "tag": latest_tag,
                "url": latest_url
            }
        }
        self.load_state(repo)

    def get_latest_version(self, repo):
        url = None
        ret = requests.get(f"{WEB}/{repo}/releases/latest")
        if ret:
            tag = ret.url.split("/")[-1]
            urls = [ f"{WEB}{''.join(e)}" for e in re.findall('"(/'+repo+'/)(\w+:{0,1}\w*@)?(\S+)(:[0-9]+)*(\.AppImage|\.appimage)"',ret.text.rstrip())]
            url = next((u for u in urls if not re.match(".*(arm|i\d{3}|aarch|linux32).*", u)), None)
        return (url,tag)

class AppActions():

    def download(self, repo):
        chunk_size = 102400
        STD.print(repo,"Downloading ...", color=STD.INFO)
        file = requests.get(self.apps[repo]["latest"]["url"], stream=True)
        length = int(float(file.headers["content-length"]))
        with open(self.apps[repo]["path"], "wb") as application:
            i = 0
            for chunk in file.iter_content(chunk_size=chunk_size):
                if chunk:
                    i += chunk_size
                    application.write(chunk)
                    STD.print_progress(repo, i, length, color=STD.INFO)
        STD.print("")
        STD.print(repo,"Application updated", color=STD.SUCCESS)
        os.chmod(self.apps[repo]["path"], 0o755)
        self.apps[repo]["current"]["url"] = self.apps[repo]["latest"]["url"]
        self.apps[repo]["current"]["tag"] = self.apps[repo]["latest"]["tag"]
        self.load_state(repo)
        self.save()

    def install(self, repo=[]):
        if type(repo) is list:
            for r in repo:
                self.install(r)
        elif type(repo) is str:
            if repo in self.apps.keys():
                STD.print(app.name,"App already exists", color=STD.ERROR)
            else:
                self.add_app(repo)
                self.check(repo)
                self.update(repo)        
            
    def remove(self, repo=[]):
        if type(repo) is list:
            for r in repo:
                self.remove(r)
        elif type(repo) is str:
            if repo in self.apps.keys():
                if os.path.exists(self.apps[repo]["path"]):
                    os.unlink(self.apps[repo]["path"])
                del self.apps[repo]
                self.save()
            else:
                STD.print(repo,"App not found", color=STD.ERROR)

    def update(self, repo=[]):
        if type(repo) is list:
            repo = repo if len(repo) > 0 else self.apps.keys()
            for r in repo:
                self.update(r)
            STD.print("","")
        elif type(repo) is str:
            if repo in self.apps.keys():
                if self.apps[repo]["state"]["need_update"]:
                    self.download(repo)
                else:
                    STD.print(repo,"UpToDate", color=STD.SUCCESS)    
            else:
                STD.print(repo,"NotFound", color=STD.ERROR)
        
    def check(self, repo=[]):
        if type(repo) is list:
            repo = repo if len(repo) > 0 else self.apps.keys()
            for r in repo:
                self.check(r)
        elif type(repo) is str:
            latest_url, latest_tag  = self.get_latest_version(repo)
            self.apps[repo]["latest"] = {
                "url": latest_url,
                "tag": latest_tag
            }
            self.load_state(repo)
            if self.apps[repo]["state"]["need_update"]:
                STD.print(repo, "New version available !", self.apps[repo]["latest"]["tag"], color=STD.WARNING)    
            else:
                STD.print(repo, "UpToDate", self.apps[repo]["latest"]["tag"],color=STD.SUCCESS)    
        self.save()


    def list(self):
        STD.print("REPO NAME", "INSTALLED", "NEED UPDATE", "CURRENT", "LATEST",color=STD.INFO)
        STD.print("---------", "---------", "-----------", "-------", "------", color=STD.INFO)
        for repo, meta in self.apps.items():
            color = STD.INFO
            if not meta["state"]["installed"]:
                color = STD.ERROR
            elif meta["state"]["need_update"]:
                color = STD.WARNING
            STD.print(repo, meta["state"]["installed"],meta["state"]["need_update"],meta["current"]["tag"], meta["latest"]["tag"],color=color)
        
    def help(self):
        STD.print("COMMANDS")
        STD.print("--------")
        STD.print("install repo_1 repo_2",           "Install one or multiple applications from Github repositories")
        STD.print("remove  repo_1 repo_2",           "Remove one or multiple applications")
        STD.print("update  repo_1 repo_2",           "Update one or multiple applications, if not specified, all applications will be updated")
        STD.print("check   repo_1 repo_2",           "Check if newer version is available for one or multiple applications, if not specified, all applications will be checked")
        STD.print("search  keyword_1 keyword_2",     "Search for an application by keywords")
        STD.print("list",     "List installed applications")

    def main(self, args):
        if len(args) > 0:
            command = args.pop(0).lower()
            if command == "install":
                self.install(args)
            elif command == "remove":
                self.remove(args)
            elif command == "update":
                self.update(args)
            elif command == "check":
                self.check(args)
            elif command == "search":
                self.search(args)
            elif command == "list":
                self.list()
            elif command == "help":
                self.help()
            else:
                STD.print("Unknown command", color=STD.ERROR)
        else:
            self.check()
            self.update()


class AppManager(AppActions, AppSearch, AppState):
    def __init__(self):
        if not os.path.exists(APPDIR):
            os.mkdir(APPDIR)
        self.load()
        self.install_appimaged()
        
    def install_appimaged(self):
        if APPIMAGED not in self.apps.keys():
            self.install(APPIMAGED)
            os.system(f'{self.apps[APPIMAGED]["path"]}')

    def load(self):
        self.apps = {}
        if os.path.exists(f'{APPDIR}/list.yaml'):
            with open(f'{APPDIR}/list.yaml') as fp:
                apps = yaml.load(fp,  Loader=yaml.FullLoader)
                for repo, meta in apps.items():
                    STD.print("Loading", repo,"", color=STD.INFO, same_line=True)
                    self.add_app(repo, meta)    
                STD.print("", "","", color=STD.INFO, same_line=True)
                STD.print("", "","", color=STD.INFO)
            
    def save(self):
        with open(f'{APPDIR}/list.yaml', mode="w") as fp:
            yaml.dump(self.apps,fp,allow_unicode=True)
                


try:
    apps = AppManager()
    args = list(sys.argv)
    args.pop(0)
    apps.main(args)
except Exception as e:
    STD.print("Something went wrong ! ",e, color=STD.ERROR)