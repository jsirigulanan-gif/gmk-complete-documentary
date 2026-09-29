from pathlib import Path
import argparse
import json

from .intake import import_research
from .storage import Project, RcloneDrive


def main():
    parser = argparse.ArgumentParser(description='GMK Drive projects (research/storage; film production not yet automated)')
    sub = parser.add_subparsers(dest='action', required=True)
    sub.add_parser('list-scripts')
    new = sub.add_parser('create')
    new.add_argument('--title', required=True)
    new.add_argument('--base', type=Path, default=Path.home() / 'GMK Projects')
    new.add_argument('--source', type=Path)
    new.add_argument('--source-url', default='')
    new.add_argument('--remote', default='gdrive:')
    new.add_argument('--drive-root', default='GMK Documentary Projects')
    for action in ('status', 'sync', 'add', 'voice'):
        p = sub.add_parser(action)
        p.add_argument('project', type=Path)
        if action == 'voice':
            p.add_argument('--limit', type=int)
            p.add_argument('--voice', default='th-TH-NiwatNeural')
        if action == 'add':
            p.add_argument('file', type=Path)
            p.add_argument('--role', required=True)
            p.add_argument('--source-url', default='')
            p.add_argument('--scene', action='append', default=[])
    args = parser.parse_args()
    if args.action == 'list-scripts':
        result = RcloneDrive().list_scripts()
    elif args.action == 'create':
        project = Project.create(args.base, args.title, source_url=args.source_url, remote=args.remote, drive_root=args.drive_root)
        if args.source:
            import_research(project, args.source)
        result = {'local_project': str(project.root), **project.read()}
    else:
        project = Project(args.project)
        if args.action == 'voice':
            from .voice import EdgeVoice, generate_voice
            result = generate_voice(project, EdgeVoice(args.voice), limit=args.limit)
        elif args.action == 'sync':
            result = project.sync()
        elif args.action == 'add':
            result = project.add_file(args.file, args.role, source_url=args.source_url, scenes=args.scene)
        else:
            result = project.read()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
