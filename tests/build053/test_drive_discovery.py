import json

from gmk_projects.storage import RcloneDrive


def test_gemini_script_discovery_accepts_plain_and_bracketed_nested_titles(monkeypatch):
    drive=RcloneDrive();calls=[]
    rows=[{'ID':'plain','Name':'lemino script.docx','Path':'research/lemino script.docx'},
          {'ID':'bracket','Name':'[LEMiNO Script] episode.docx'},
          {'ID':'spaced','Name':'  LEMINO   SCRIPT research.docx'},
          {'ID':'unrelated','Name':'A different script.docx'},
          {'ID':'similar','Name':'lemino scripting.txt'},
          {'Name':'lemino script missing-id.docx'}]
    def run(*args,**kwargs):
        calls.append(args);return json.dumps(rows)
    monkeypatch.setattr(drive,'_run',run)
    found=drive.list_scripts()
    assert [r['ID'] for r in found]==['plain','bracket','spaced']
    assert found[0]['Path']=='research/lemino script.docx' and '--recursive' in calls[0]
