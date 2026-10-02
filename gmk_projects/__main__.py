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
                   'footage-search', 'footage-download', 'delivery-verify', 'delivery-sync',
                   'production-inspect', 'production-connect-story', 'media-inspect', 'media-connect', 'coverage-inspect', 'coverage-record',
                   'workflow', 'brief-save', 'shot-review', 'voice-review', 'research-add-claim',
                   'final-inspect', 'final-prepare', 'final-voice-decide', 'final-reopen',
                   'design-inspect', 'design-prepare', 'design-decide', 'design-reopen', 'plan-prepare',
                   'preproduction-inspect', 'review-prepare', 'review-decide', 'lock-prepare', 'lock-decide', 'preproduction-reopen', 'production-render'):
        p = sub.add_parser(action)
        p.add_argument('project', type=Path)
        if action == 'research-add-claim':
            p.add_argument('--source-path', required=True)
            p.add_argument('--excerpt', required=True)
            p.add_argument('--claim', required=True)
        if action == 'voice':
            p.add_argument('--limit', type=int)
            p.add_argument('--voice', default='th-TH-NiwatNeural')
        if action == 'edit-voice':
            p.add_argument('--allow-online-tts', action='store_true')
            p.add_argument('--voice', default='th-TH-NiwatNeural')
            p.add_argument('--scene', action='append')
        if action == 'editorial-approve':
            p.add_argument('--master-sha256', required=True)
            from .workflow import FILM_CHECKS
            p.add_argument('--review-check', action='append', choices=tuple(FILM_CHECKS))
        if action == 'brief-save':
            for field in ('topic', 'audience', 'central-question'):
                p.add_argument('--'+field, required=True)
            p.add_argument('--target-seconds', type=int, required=True)
            p.add_argument('--scope', default='')
            p.add_argument('--revision', type=int, required=True)
        if action in ('shot-review', 'voice-review'):
            p.add_argument('--scene', required=True)
            p.add_argument('--revision', type=int, required=True)
        if action == 'shot-review':
            p.add_argument('--shot', required=True)
            p.add_argument('--visible-content', required=True)
            p.add_argument('--match-reason', required=True)
            p.add_argument('--match-type', choices=('DIRECT', 'SUPPORTING', 'CONTEXT'), required=True)
        if action in ('production-connect-story', 'media-connect', 'coverage-record', 'final-prepare', 'final-voice-decide', 'final-reopen',
                      'design-prepare', 'design-decide', 'design-reopen', 'plan-prepare',
                      'review-prepare', 'review-decide', 'lock-prepare', 'lock-decide', 'preproduction-reopen', 'production-render'):
            p.add_argument('--edit-sha256', required=True)
            p.add_argument('--manifest-sha256', required=True)
        if action == 'coverage-record':
            p.add_argument('--complete-library-selection', action='store_true')
            p.add_argument('--stop-reason', default='')
        if action == 'final-voice-decide':
            p.add_argument('--master-sha256', required=True)
            p.add_argument('--decision', choices=('APPROVED', 'REJECTED'), required=True)
            p.add_argument('--actor-id', required=True)
        if action in ('design-decide', 'review-decide', 'lock-decide'):
            p.add_argument('--decision', choices=('APPROVED', 'REJECTED'), required=True)
            p.add_argument('--actor-id', required=True)
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
        if args.action == 'research-add-claim':
            from .research_draft import add_review_claim
            result = add_review_claim(project, args.source_path, args.excerpt, args.claim)
        elif args.action == 'workflow':
            from .workflow import workflow_status
            result = workflow_status(project)
        elif args.action == 'brief-save':
            from .brief import save_brief
            result = save_brief(project, topic=args.topic, audience=args.audience, central_question=args.central_question,
                                target_seconds=args.target_seconds, scope=args.scope, expected_revision=args.revision)
        elif args.action in ('shot-review', 'voice-review'):
            from .media_review import review_shot, review_voice
            result = (review_voice(project, args.scene, expected_revision=args.revision) if args.action == 'voice-review'
                      else review_shot(project, args.scene, args.shot, visible_content=args.visible_content,
                                       match_reason=args.match_reason, match_type=args.match_type, expected_revision=args.revision))
        elif args.action in ('edit-init', 'edit-preflight', 'edit-voice'):
            from .edit import EditSession, EditError
            session = EditSession(project)
            if args.action == 'edit-voice':
                if not args.allow_online_tts:
                    raise EditError('Use --allow-online-tts to explicitly permit sending narration to Microsoft Edge TTS')
                from .voice import EdgeVoice
                result = session.synthesize(EdgeVoice(args.voice), scene_ids=args.scene)
            else:
                result = session.load() if args.action == 'edit-init' else session.preflight()
        elif args.action in ('production-inspect', 'production-connect-story'):
            from .production_bridge import inspect_story, connect_story
            result = inspect_story(project) if args.action == 'production-inspect' else connect_story(
                project, expected_edit_sha256=args.edit_sha256, expected_manifest_sha256=args.manifest_sha256)
        elif args.action in ('media-inspect', 'media-connect'):
            from .media_bridge import inspect_media, connect_media
            result = inspect_media(project) if args.action == 'media-inspect' else connect_media(
                project, expected_edit_sha256=args.edit_sha256, expected_manifest_sha256=args.manifest_sha256)
        elif args.action in ('coverage-inspect', 'coverage-record'):
            from .coverage import inspect_coverage, record_coverage
            result = inspect_coverage(project) if args.action == 'coverage-inspect' else record_coverage(project,
                expected_edit_sha256=args.edit_sha256, expected_manifest_sha256=args.manifest_sha256,
                complete_selection=args.complete_library_selection, stop_reason=args.stop_reason)
        elif args.action in ('final-inspect', 'final-prepare', 'final-voice-decide', 'final-reopen'):
            from .final_production import inspect_final, prepare_final, decide_final_voice, reopen_final
            if args.action == 'final-inspect': result = inspect_final(project)
            elif args.action == 'final-prepare': result = prepare_final(project,
                expected_edit_sha256=args.edit_sha256, expected_manifest_sha256=args.manifest_sha256)
            elif args.action == 'final-reopen': result = reopen_final(project,
                expected_edit_sha256=args.edit_sha256, expected_manifest_sha256=args.manifest_sha256)
            else: result = decide_final_voice(project, expected_edit_sha256=args.edit_sha256,
                expected_manifest_sha256=args.manifest_sha256, expected_master_sha256=args.master_sha256,
                decision=args.decision, actor_id=args.actor_id)
        elif args.action in ('design-inspect', 'design-prepare', 'design-decide', 'design-reopen', 'plan-prepare'):
            from .design_planning import inspect_design, prepare_design, decide_design, reopen_design, prepare_plans
            if args.action == 'design-inspect': result = inspect_design(project)
            else:
                operation = {'design-prepare': prepare_design, 'design-decide': decide_design,
                             'design-reopen': reopen_design, 'plan-prepare': prepare_plans}[args.action]
                kwargs = {'decision': args.decision, 'actor_id': args.actor_id} if args.action == 'design-decide' else {}
                result = operation(project, expected_edit_sha256=args.edit_sha256,
                    expected_manifest_sha256=args.manifest_sha256, **kwargs)
        elif args.action in ('preproduction-inspect', 'review-prepare', 'review-decide', 'lock-prepare', 'lock-decide', 'preproduction-reopen', 'production-render'):
            from .preproduction import inspect_preproduction, prepare_review, decide_review, prepare_lock, decide_lock, reopen_preproduction
            from .production_render import render_production
            if args.action == 'preproduction-inspect': result = inspect_preproduction(project)
            else:
                operation = {'review-prepare': prepare_review, 'review-decide': decide_review, 'lock-prepare': prepare_lock,
                             'lock-decide': decide_lock, 'preproduction-reopen': reopen_preproduction, 'production-render': render_production}[args.action]
                kwargs = {'decision': args.decision, 'actor_id': args.actor_id} if args.action in ('review-decide', 'lock-decide') else {}
                result = operation(project, expected_edit_sha256=args.edit_sha256, expected_manifest_sha256=args.manifest_sha256, **kwargs)
        elif args.action in ('delivery-verify', 'delivery-sync'):
            from .delivery import verify_delivery, deliver_project
            result = (verify_delivery if args.action == 'delivery-verify' else deliver_project)(project)
        elif args.action in ('render', 'editorial-approve', 'delivery'):
            from .render import render_project, approve_editorial_review, export_delivery
            result = (render_project(project) if args.action == 'render' else
                      approve_editorial_review(project, expected_master_sha256=args.master_sha256,
                                              checklist={k: True for k in args.review_check} if args.review_check is not None else None)
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
