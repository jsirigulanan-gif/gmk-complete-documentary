from pathlib import Path
import argparse
import json

from .intake import import_research
from .storage import Project, RcloneDrive


def main():
    parser = argparse.ArgumentParser(description='GMK documentary project research, editing, media, render and draft delivery')
    sub = parser.add_subparsers(dest='action', required=True)
    sub.add_parser('list-scripts')
    new = sub.add_parser('create')
    new.add_argument('--title', required=True)
    new.add_argument('--base', type=Path, default=Path.home() / 'GMK Projects')
    new.add_argument('--source', type=Path)
    new.add_argument('--source-url', default='')
    new.add_argument('--remote', default='gdrive:')
    new.add_argument('--drive-root', default='GMK Documentary Projects')
    for action in ('status', 'sync', 'add', 'voice', 'connect-production', 'research-intake', 'research-review',
                   'edit-init', 'edit-preflight', 'edit-voice', 'render', 'editorial-approve', 'delivery',
                   'footage-search', 'footage-download', 'delivery-verify', 'delivery-sync'):
        p = sub.add_parser(action)
        p.add_argument('project', type=Path)
        if action == 'voice':
            p.add_argument('--limit', type=int)
            p.add_argument('--voice', default='th-TH-NiwatNeural')
        if action == 'edit-voice':
            p.add_argument('--allow-online-tts', action='store_true')
            p.add_argument('--voice', default='th-TH-NiwatNeural')
            p.add_argument('--scene', action='append')
        if action == 'editorial-approve':
            p.add_argument('--master-sha256', required=True)
        if action == 'footage-search':
            p.add_argument('--query', required=True)
        if action == 'footage-download':
            p.add_argument('--url', required=True)
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
        if args.action in ('edit-init', 'edit-preflight', 'edit-voice'):
            from .edit import EditSession, EditError
            session = EditSession(project)
            if args.action == 'edit-voice':
                if not args.allow_online_tts:
                    raise EditError('Use --allow-online-tts to explicitly permit sending narration to Microsoft Edge TTS')
                from .voice import EdgeVoice
                result = session.synthesize(EdgeVoice(args.voice), scene_ids=args.scene)
            else:
                result = session.load() if args.action == 'edit-init' else session.preflight()
        elif args.action in ('delivery-verify', 'delivery-sync'):
            from .delivery import verify_delivery, deliver_project
            result = (verify_delivery if args.action == 'delivery-verify' else deliver_project)(project)
        elif args.action in ('render', 'editorial-approve', 'delivery'):
            from .render import render_project, approve_editorial_review, export_delivery
            result = (render_project(project) if args.action == 'render' else
                      approve_editorial_review(project, expected_master_sha256=args.master_sha256)
                      if args.action == 'editorial-approve' else export_delivery(project))
        elif args.action in ('footage-search', 'footage-download'):
            from .footage import search_footage, acquire_footage, candidate_from_url
            result = (search_footage(project, args.query) if args.action == 'footage-search' else
                      acquire_footage(project, candidate_from_url(args.url)))
        elif args.action in ('research-intake', 'research-review'):
            from .research import analyze_research, research_review
            result = (analyze_research if args.action == 'research-intake' else research_review)(project)
        elif args.action == 'connect-production':
            from .production import ProductionProject
            result = ProductionProject(project).connect_existing()
        elif args.action == 'voice':
            from .voice import EdgeVoice, generate_voice
            result = generate_voice(project, EdgeVoice(args.voice), limit=args.limit)
        elif args.action == 'sync':
            result = project.sync()
        elif args.action == 'add':
            result = project.add_file(args.file, args.role, source_url=args.source_url, scenes=args.scene)
        else:
            from .production import ProductionProject
            result = {**project.read(), 'production': ProductionProject(project).status()}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
