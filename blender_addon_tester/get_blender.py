import os
import stat
import sys
import shutil
import subprocess
import zipfile
import tarfile
import requests
import re
from glob import glob
from bs4 import BeautifulSoup
from distutils.dir_util import copy_tree

CURRENT_MODULE_DIRECTORY = os.path.abspath(os.path.dirname(__file__))

def is_mac_intel(x):
    machine = "(macOS|darwin)"
    ext = "(dmg|zip|tar\.gz)"
    return re.search(machine, x) and re.search(f"{ext}$", x) and re.search("x86|x64", x)

def is_mac_arm(x):
    machine = "(macOS|darwin)"
    ext = "(dmg|zip|tar\.gz)"
    return re.search(machine, x) and re.search(f"{ext}$", x) and re.search("arm64", x)

def is_windows(x):
    machine = "windows"
    ext = "zip"
    return re.search(machine, x) and re.search(f"{ext}$", x) and re.search("amd64", x)

def is_linux(x):
    machine = "linux"
    ext = "tar.(xz|gz|bz2)"
    return re.search(machine, x) and re.search(f"{ext}$", x) and re.search("x86", x)

def first_link(links, check):
    for link in links:
        link_string = str(link.get("href"))
        if check(link_string):
            return link_string
    return None


def getSuffix(blender_version, platform=None):
    
    if platform is None:
        platform = sys.platform
    print(platform)
    
    
    if "win32" == platform or "win64" == platform or "cygwin" == platform:
        platform = "windows"
    elif "darwin" == platform:
        platform = "mac_intel"
    else:
        platform = "linux"
    
    find_func = {
        "windows" : is_windows, 
        "mac_intel" : is_mac_intel,
        "mac_arm" : is_mac_arm, 
        "linux" : is_mac_arm
    }
    
    g = re.search(f"\d\.\d+", blender_version)
    
    if g:
        rev = g.group(0)
    else:
        raise RuntimeError(f"Blender version cannot be guessed in the following string: {blender_version}")
        
    urls = [
        "https://builder.blender.org/download/daily"
    ]
    
    blender_zippath = None
    nightly = False
    release_file_found = False
    versions_found = {}
    links = {}
    for url in urls:
        versions_found[url] = []
        if release_file_found:
            break

        print(f"FETCHING RELEASES FROM: {url}")
        page = requests.get(url)
        soup = BeautifulSoup(page.text, features="html.parser")
        
        blender_version_suffix = ""
        link = first_link(soup.find_all("a"), find_func.get(platform))
        print("This is the link" + str(link))
        if not link:
            raise Exception("Unable to find a suitable blender version to download.")
        
        if link.startswith("https"):
            blender_zippath = f"{links[rev]}"
        else:
            blender_zippath = f"{url}/{links[rev]}"
    print(blender_zippath)
    print(nightly)
    return blender_zippath, nightly

def findMacOSContentsParentDirectory(starting_path):
    cwd = os.getcwd()
    osx_mounted_contents_parent = None
    for root, dirs, files in os.walk(starting_path):
        if osx_mounted_contents_parent:
            break
        # print(f"root is {root}")
        if os.path.basename(root) == "Contents" and "blender.app" in root.lower():
            osx_mounted_contents_parent = os.path.realpath(os.path.dirname(root))
            print("Found Contents parent", os.path.realpath(osx_mounted_contents_parent))
            print("Contents of Contents/:", os.listdir(root))
            break
        path = root.split(os.sep)
        # print((len(path) - 1) * '---', os.path.basename(root))
        for file in files:
            #print(len(path) * '---', file)
            pass
    
    if not osx_mounted_contents_parent:
        print(f"Error, could not find some [bB]lender.app/Contents directory in downloaded {blender_zipfile} dmg archive")
        exit(1)

    os.chdir(cwd)
    
    return osx_mounted_contents_parent
 


def getBlender(blender_version, blender_zippath, nightly):
    """ Downloads Blender v'blender_version'//'nightly' if not yet in cache. Returns a decompressed Blender release path.
    """
    print(f"About to try to download Blender {blender_version} from {blender_zippath} nightly: {nightly}")
    remove = False
    cwd = os.getcwd()
    if "BLENDER_CACHE" in os.environ.keys():
        print(f"BLENDER_CACHE environment variable found {os.environ['BLENDER_CACHE']}")
        cache_path = os.path.expanduser(os.environ["BLENDER_CACHE"])
        if not os.path.exists(cache_path):
            print(f"Creating cache directory: {cache_path}")
            os.makedirs(cache_path)
        else:
            print(f"Cache directory already exists: {cache_path}")
    else:
        cache_path = ".."
    os.chdir(cache_path)
    
    cache_dir = os.getcwd()

    ext = ""
    if nightly == True:
        ext = "-nightly"
    dst = os.path.join(cache_dir, f"blender-{blender_version}{ext}")

    if os.path.exists(dst):
        if nightly == True or remove:
            print(f"Removing directory (nightly:{nightly}, remove:{remove}): {dst}")
            shutil.rmtree(dst)
        else:
            print(f"Blender {blender_version} (non-nightly) release found at: {dst}")
            os.chdir(cwd)
            return dst

    blender_zipfile = blender_zippath.split("/")[-1]

    files = glob(blender_zipfile)

    is_osx_archive = False

    if 0 == len(files):
        if not os.path.exists(blender_zipfile):
            r = requests.get(blender_zippath, stream=True)
            print(f"Downloading {blender_zippath}")
            open(blender_zipfile, "wb").write(r.content)

    if blender_zipfile.endswith("zip"):
        z = zipfile.ZipFile(blender_zipfile, "r")
        zfiles = z.namelist()
        zdir = zfiles[0].split("/")[0]
    elif blender_zipfile.endswith("dmg"):
        is_osx_archive = True
        from dmglib import attachedDiskImage
        with attachedDiskImage(blender_zipfile) as mounted_dmg:
            print(f"Mounted {blender_zipfile}")
            osx_mounted_contents_parent = findMacOSContentsParentDirectory(mounted_dmg[0])
            print(f'Copying Blender out of mounted space from {osx_mounted_contents_parent} to {cache_dir}...')
            copy_tree(osx_mounted_contents_parent, cache_dir)
        os.chdir(cache_dir)
        zdir = os.path.join(cache_dir, "Contents")
        print("DEBUG: zdir is:", zdir)
        print("DEBUG: is zdir a dir?", os.path.isdir(zdir))
    elif blender_zipfile.endswith("tar.bz2") or blender_zipfile.endswith("tar.gz") or blender_zipfile.endswith("tar.xz"):
        z = tarfile.open(blender_zipfile)
        zfiles = z.getnames()
        zdir = zfiles[0].split("/")[0]
    else:
        print("Error, unknown archive extension: {blender_zipfile}. Will not extract it.}")
        exit(1)

    if not os.path.isdir(zdir):
        # OSX directories are not always recognized by os.path.isdir, so skipping OSX situations here
        print(f"Unpacking {blender_zipfile}")
        z.extractall()
        z.close()

    if not is_osx_archive:
        # Some non-dmg archives may abnormally contain an OSX release
        # Example cases: 
        # https://ftp.nluug.nl/pub/graphics/blender/release/Blender2.78/blender-2.78c-OSX_10.6-x86_64.zip
        # https://download.blender.org/release/Blender2.79/blender-2.79-macOS-10.6.tar.gz
        for zfile in zfiles:
            if re.search(".*OSX.*|.lender\.app", zfile):
                print("Detected old-style type of MacOSX release: a .zip/.tar.gz archive (instead of .dmg) containing a directory.")
                is_osx_archive = True
                print("CWD IS:", os.getcwd())
                print("CWD listdir:", os.listdir())
                osx_extracted_contents_dir = os.path.join(findMacOSContentsParentDirectory(os.getcwd()), "Contents")
                print("contents dir:", osx_extracted_contents_dir)
                zdir = os.path.realpath(osx_extracted_contents_dir)
                print("new zdir:", zdir)
                break

    blender_archive = os.path.realpath(zdir)

    # Directories for MacOSX have a special structure, search for blender and python executables and change permissions
    if is_osx_archive:
        print("OSX DETECTED, current dir is:", os.getcwd())
        print("OSX DETECTED, files in current dir:", os.listdir("."))
        print("OSX DETECTED, files in zdir:", os.listdir(zdir))
        expected_executable_dir = os.path.realpath(os.path.join(zdir, "MacOS"))
        executable_path = glob(f"{expected_executable_dir}/*lender")
        if executable_path:
            executable_path = executable_path[0]
            print("Blender MacOS executable found at:", executable_path)
            print("Adding executable rights to MacOS blender binary file")
            os.chmod(executable_path, stat.S_IXOTH | stat.S_IXGRP | stat.S_IXUSR)
        else:
            print("Error, Blender MacOS executable not found in directory:", expected_executable_dir, "glob result:", executable_path, "files in target directory:", os.listdir(expected_executable_dir))
            exit(1)
 
        zfiles = []
        for root, directories, filenames in os.walk(zdir):
            for filename in filenames:
                zfiles.append(os.path.realpath(os.path.join(root,filename)))

    python = None
    for zfile in zfiles:
        if re.search("bin/python.exe", zfile) or re.search("bin/python\d.\dm?", zfile):
            python = os.path.realpath(zfile)
            print(f"Blender's bundled python executable was found: {python}")
            print("Adding executable rights to blender bundled python binary file")
            os.chmod(python, os.stat(python).st_mode | stat.S_IXOTH | stat.S_IXGRP | stat.S_IXUSR)
            break
    if not python:
        print("ERROR, Blender's bundled python executable could not be found within Blender's files")
        exit(1)

    cmd = f"{python} -m ensurepip"
    os.system(cmd)

    cmd = f"{python} -m pip install -U pip"
    os.system(cmd)

    cmd = f"{python} -m pip install --upgrade -r {CURRENT_MODULE_DIRECTORY}/blender_requirements.txt -r {CURRENT_MODULE_DIRECTORY}/requirements.txt"
    os.system(cmd)


    shutil.rmtree("tests/__pycache__", ignore_errors=True)

    src = blender_archive
    print(f"Move {src} to {dst}")
    shutil.move(src, dst)
    os.chdir(cwd)

    return dst


def get_blender_from_suffix(blender_version):
    print(f"Request to get Blender from suffix, with blender_version: {blender_version}")

    blender_zipfile, nightly = getSuffix(blender_version)

    return getBlender(blender_version, blender_zipfile, nightly)


if __name__ == "__main__":
    if "cygwin" == sys.platform:
        print("ERROR, do not run this under cygwin, run it under Linux and Windows cmd!!")
        exit(1)

    if len(sys.argv) > 1:
        blender_rev = sys.argv[1]
    else:
        blender_rev = "2.92"

    if re.search("-", blender_rev):
        blender_rev, _ = blender_rev.split("-")

    get_blender_from_suffix(blender_rev)
