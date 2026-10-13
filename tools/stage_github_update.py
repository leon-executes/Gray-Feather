"""Copy this release into a clean local Git clone. Does not commit or push."""
import argparse, json, shutil, subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def git(target,*args):
    return subprocess.check_output(['git','-C',str(target),*args],text=True).strip()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('clone',type=Path)
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args();target=args.clone.resolve()
    if target==ROOT or Path(git(target,'rev-parse','--show-toplevel')).resolve()!=target:
        raise ValueError('Choose the root of a separate local Git clone.')
    if git(target,'status','--porcelain'):
        raise ValueError('The clone has local changes. Commit or preserve them before updating.')
    inventory=json.loads((ROOT/'packaging/repository-files.json').read_text(encoding='utf-8'))['files']
    moved=json.loads((ROOT/'packaging/source-moves.json').read_text(encoding='utf-8'))
    moved=set(moved)|set(json.loads((ROOT/'packaging/source-removals.json').read_text(encoding='utf-8')))
    for name in set(inventory)|set(moved):
        if not (target/name).resolve().is_relative_to(target) or name.startswith('.git/'):
            raise ValueError('Unsafe repository path: '+name)
    if not args.apply:
        print(f'Ready: copy {len(inventory)} release files; remove {len(moved)} old source paths. Add --apply to proceed.');return
    for name in inventory:
        destination=target/name;destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/name,destination)
    for name in moved:
        old=target/name
        if old.is_file() and name not in inventory:old.unlink()
    print('Release files copied. Review the changes in GitHub Desktop, commit and push. No commit or upload was performed.')

if __name__=='__main__':main()
