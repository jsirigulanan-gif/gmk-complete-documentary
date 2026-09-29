from gmk_footage.web_sources import NasaMediaProvider,InternetArchiveProvider,WikimediaStillProvider


def test_nasa_video_and_image_normalization():
 def fetch(url):return {'collection':{'items':[{'href':'collection','data':[{'nasa_id':'X1','title':'Apollo test','description':'Moon footage','photographer':'NASA'}],'links':[{'href':'https://example/video.mp4','render':'video'}]}]}}
 v=NasaMediaProvider(fetch).search('apollo',media_type='video',limit=2)[0]
 assert v.source_priority=='WEB_VIDEO' and v.media_url.endswith('.mp4')
 i=NasaMediaProvider(fetch).search('apollo',media_type='image',limit=2)[0]
 assert i.source_priority=='STILL_DOCUMENT'


def test_archive_normalization():
 def fetch(url):return {'response':{'docs':[{'identifier':'abc','title':'Historic film','creator':'Archive Creator','description':'old film'}]}}
 x=InternetArchiveProvider(fetch).search('history')[0]
 assert x.page_url=='https://archive.org/details/abc' and x.source_priority=='WEB_VIDEO'


def test_wikimedia_normalization():
 def fetch(url):return {'query':{'pages':{'1':{'index':1,'title':'File:Photo.jpg','imageinfo':[{'url':'https://upload.wikimedia.org/photo.jpg','extmetadata':{'Artist':{'value':'Jane'},'ImageDescription':{'value':'A photo'},'LicenseShortName':{'value':'CC BY-SA'}}}]}}}}
 x=WikimediaStillProvider(fetch).search('photo')[0]
 assert x.media_url.endswith('photo.jpg') and x.license_text=='CC BY-SA' and x.source_priority=='STILL_DOCUMENT'
