from gmk_footage.query_planner import BeatSearchIntent
from gmk_footage.transcript import parse_vtt_text, TranscriptTimestampFinder

VTT='''WEBVTT

00:00:01.000 --> 00:00:05.000
Welcome to the show.

00:00:20.000 --> 00:00:25.000
Hideo Kojima had every intention of being with us tonight.

00:00:25.000 --> 00:00:31.000
Unfortunately he was informed by a lawyer representing Konami that he would not be allowed to travel.

00:00:31.000 --> 00:00:36.000
This is The Game Awards 2015.

00:01:00.000 --> 00:01:03.000
Thank you everyone.
'''

def _intent():
 return BeatSearchIntent('BEAT_TGA',{'id':'NB','version':1},'CRITICAL',
  'Geoff Keighley speaking at The Game Awards 2015 about Hideo Kojima',
  'Kojima was absent from the stage',({'id':'C','version':1},),
  ('Hideo Kojima was not allowed to attend The Game Awards 2015',),('The Game Awards 2015',),
  ('Geoff Keighley','Hideo Kojima','Game Awards','2015'),
  ({'family':'EXACT_ENTITY','query':'q'},),('YOUTUBE','WEB_VIDEO','STILL_DOCUMENT','AI_GENERATED'),True)


def test_vtt_parser_and_timestamp_match():
 cues=parse_vtt_text(VTT)
 assert len(cues)==5
 matches=TranscriptTimestampFinder.find(_intent(),cues,window_seconds=20)
 assert matches
 best=matches[0]
 assert 18 <= best.start <= 21
 assert best.end >= 36
 assert 'kojima' in best.matched_terms
 assert best.score>0.2


def test_no_match_returns_empty():
 cues=parse_vtt_text('WEBVTT\n\n00:00:01.000 --> 00:00:03.000\nCooking pasta tonight\n')
 assert TranscriptTimestampFinder.find(_intent(),cues)==()
