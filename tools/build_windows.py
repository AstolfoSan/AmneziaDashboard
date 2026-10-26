"""Build the Windows x64 wizard from sanitized source, never private deployments."""
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'installer'))
from branding import icon_ico


def build():
    if os.name!='nt' or platform.machine().lower() not in {'amd64','x86_64'}:raise SystemExit('Build on Windows x64')
    output=ROOT/'dist';work=ROOT/'build/windows';output.mkdir(exist_ok=True);work.mkdir(parents=True,exist_ok=True)
    target=output/'AmneziaDashboardSetup.exe'
    if target.exists():raise SystemExit('Refusing to overwrite an existing EXE')
    version=(ROOT/'VERSION').read_text().strip();numbers=tuple(int(v) for v in version.split('.'))+(0,)
    resource=work/'version.txt'
    resource.write_text("VSVersionInfo(ffi=FixedFileInfo(filevers="+repr(numbers)+",prodvers="+repr(numbers)+",mask=0x3f,flags=0,OS=0x40004,fileType=1,subtype=0,date=(0,0)),kids=[StringFileInfo([StringTable('040904B0',[StringStruct('CompanyName','AmneziaDashboard contributors'),StringStruct('FileDescription','AmneziaDashboard Setup'),StringStruct('FileVersion','"+version+"'),StringStruct('ProductName','AmneziaDashboard'),StringStruct('ProductVersion','"+version+"'),StringStruct('OriginalFilename','AmneziaDashboardSetup.exe')])]),VarFileInfo([VarStruct('Translation',[1033,1200])])])",encoding='utf-8')
    licenses=work/'licenses';licenses.mkdir(exist_ok=True)
    packages={}
    for dist in importlib.metadata.distributions():
        name=dist.metadata['Name'];packages[name]=dist.version
        for item in dist.files or []:
            if item.name.lower().startswith(('license','copying','notice','authors')) and '.dist-info' in str(item):
                destination=licenses/(name+'-'+str(item).split('.dist-info/',1)[-1].replace('/','_'))
                destination.write_bytes(dist.locate_file(item).read_bytes())
    for name,source in [('Python-LICENSE.txt',Path(sys.base_prefix)/'LICENSE.txt'),
                        ('Tcl-license.txt',ROOT/'docs/licenses/tcl-license.txt'),
                        ('Tk-license.txt',ROOT/'docs/licenses/tk-license.txt')]:
        if not source.is_file():raise SystemExit('Missing runtime license: '+name)
        (licenses/name).write_bytes(source.read_bytes())
    (licenses/'AmneziaDashboard-LICENSE.txt').write_bytes((ROOT/'LICENSE').read_bytes())
    (licenses/'BUILD.json').write_text(json.dumps({'python':platform.python_version(),'platform':'Windows x64','packages':packages},indent=2),encoding='utf-8')
    icon=work/'dashboard.ico';icon.write_bytes(icon_ico())
    args=[sys.executable,'-m','PyInstaller','--onefile','--windowed','--noupx','--icon',str(icon),'--version-file',str(resource),
          '--name','AmneziaDashboardSetup','--distpath',str(output),'--workpath',str(work/'pyinstaller'),'--specpath',str(work),
          '--paths',str(ROOT/'installer'),'--collect-all','paramiko','--collect-all','cryptography','--collect-all','bcrypt','--collect-all','nacl']
    for source,dest in [('installer/portable','portable'),('installer/messages_en.json','.'),('installer/node_install.py','.'),
                        ('installer/relay.py','.'),('installer/vpn_runtime.py','.'),('build/windows/licenses','licenses')]:
        args+=['--add-data',str(ROOT/source)+os.pathsep+dest]
    args.append(str(ROOT/'installer/installer.py'))
    subprocess.run(args,cwd=ROOT,check=True)
    report=work/'selftest.json'
    result=subprocess.run([str(target),'--self-test','--report',str(report)],timeout=90,check=True)
    if json.loads(report.read_text())!={'version':(ROOT/'VERSION').read_text().strip(),'passed':True,'vps_accessed':False}:raise SystemExit('Frozen self-test failed')
    with zipfile.ZipFile(output/'Windows-licenses.zip','x',zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(licenses.iterdir()):archive.write(path,path.name)
    names=['AmneziaDashboard.zip','AmneziaDashboardSetup.exe','Windows-licenses.zip']
    (output/'SHA256SUMS').write_text(''.join(hashlib.sha256((output/name).read_bytes()).hexdigest()+'  '+name+'\n' for name in names),encoding='ascii')
    print(json.dumps({'version':(ROOT/'VERSION').read_text().strip(),'windows_x64_build':True,'frozen_self_test':True,'code_signed':False,'vps_accessed':False}))


if __name__=='__main__':build()
