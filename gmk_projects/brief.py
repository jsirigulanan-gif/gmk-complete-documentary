"""Editable documentary brief kept with the working draft."""
from .edit import EditError, EditSession


def save_brief(project, *, topic, audience, central_question, target_seconds,
               scope='', expected_revision):
    values = (topic, audience, central_question)
    if any(not isinstance(v, str) or not v.strip() for v in values):
        raise EditError('ระบุหัวเรื่อง กลุ่มผู้ชม และคำถามหลักให้ครบ')
    if isinstance(target_seconds, bool) or not isinstance(target_seconds, int) or not 30 <= target_seconds <= 3600:
        raise EditError('ความยาวเป้าหมายต้องเป็นจำนวนเต็ม 30–3600 วินาที')
    session = EditSession(project)
    edit = session.load()
    edit['title'] = topic.strip()
    edit['central_question'] = central_question.strip()
    edit['brief'] = {'topic': topic.strip(), 'audience': audience.strip(),
                     'central_question': central_question.strip(), 'target_seconds': target_seconds,
                     'scope': scope.strip(), 'language': 'th-TH'}
    return session.save(edit, expected_revision=expected_revision)
