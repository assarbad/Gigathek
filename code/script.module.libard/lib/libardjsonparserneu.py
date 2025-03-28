#!/usr/bin/python
# -*- coding: utf-8 -*-
import sys
import json
import re
import libmediathek3 as libMediathek
import libmediathek3utils as utils
import xbmcaddon

if sys.version_info[0] < 3: # for Python 2
	from urllib import urlencode
else: # for Python 3
	from urllib.parse import urlencode
	from functools import reduce

addon = xbmcaddon.Addon()

baseUrlJsonDirect = 'https://api.ardmediathek.de/page-gateway/pages/'
baseUrlProgramAPI = 'https://programm-api.ard.de/program/api/program?day='
baseUrlDocuments = 'https://api.ardmediathek.de/page-gateway/pages/ard/item/'

pageIndexAZPage = 0
pageIndexProgramPage = 1
pageIndexLivestreamPage = 2
pageIndexShowPage = 3


def deep_get(dictionary, keys, default=None):
	return reduce(lambda d, key: d.get(key, default) if isinstance(d, dict) else default, keys.split('.'), dictionary)


def parseLivestreams(partnerKey, clientKey):
	pageIndex = pageIndexLivestreamPage
	url = baseUrlJsonDirect + clientKey + '/home'
	result = parse(pageIndex, url, partnerKey)
	snapshot_file = 'livestream.' + (partnerKey if partnerKey else clientKey) +'.json'
	utils.f_mkdir(utils.pathUserdata(''))
	if result:
		utils.f_write(utils.pathUserdata(snapshot_file), json.dumps(result))
	else:
		try:
			res = json.loads(utils.f_open(utils.pathUserdata(snapshot_file)))
			for item in res:
				item['name'] += ' (Snapshot)'
			result = res 
		except:
			pass
	return result


def parseAZ(partnerKey, clientKey, letter):
	pageIndex = pageIndexAZPage
	url = baseUrlJsonDirect + clientKey + '/editorial/experiment-a-z'
	return parse(pageIndex, url, partnerKey, None, letter)


def parseShow(showId):
	pageIndex = pageIndexShowPage
	url = baseUrlJsonDirect + 'ard/grouping/' + showId
	return parse(pageIndex, url)


def parseDate(partnerKey, clientKey, date):
	pageIndex = pageIndexProgramPage
	url = baseUrlProgramAPI + date  # date = YYYY-MM-DD
	channelKey = clientKey if partnerKey else None
	return parse(pageIndex, url, partnerKey, channelKey)


def getVideoUrl(url):
	result = None
	response = libMediathek.getUrl(url)
	j = json.loads(response)
	widgets = j.get('widgets',None)
	if widgets:
		for widget in widgets:
			if widget.get('type','').startswith('player'):
				mediaCollection = deep_get(widget, 'mediaCollection.embedded._mediaArray')
				result = extract (mediaCollection)
				if not result:
					mediaCollection = deep_get(widget, 'mediaCollection.embedded._alternativeMediaArray')
					if mediaCollection and isinstance(mediaCollection,list) and isinstance(mediaCollection[0],dict):
						result = extract (mediaCollection[0].get('_mediaArray', []))
	return result


def parseSearchAPI(search_string):
	l = []
	try:
		response = libMediathek.getUrl('http://api.ardmediathek.de/page-gateway/widgets/ard/search/vod?searchString='+search_string)
		j = json.loads(response)
		for item in j.get('teasers',[]):
			if isinstance(item,dict) and (item.get('type',None) == 'ondemand'):
				id = item.get('id',None)
				name = item['shortTitle']
				if id and name:
					d ={}
					d['documentId'] = id
					d['url'] = baseUrlDocuments + id
					d['duration'] = str(item.get('duration',None))
					d['name'] = deep_get(item, 'show.title')
					if d['name']:
						d['name'] = d['name'] + ' | ' + name
					else:
						d['name'] = name
					d['plot'] = item.get('longTitle',None)
					availableTo = item.get('availableTo',None)
					if availableTo:
						d['plot'] = '[COLOR blue]' + addon.getLocalizedString(32013) + ' ' + libMediathek.str_to_airedtime(availableTo).strftime('%d.%m.%Y')  + ' | [/COLOR]' + d.get('plot','')
					broadcastedOn = item.get('broadcastedOn',None)
					if broadcastedOn:
						d['plot'] = '[COLOR blue]' + addon.getLocalizedString(32012) + ' ' + libMediathek.str_to_airedtime(broadcastedOn).strftime('%d.%m.%Y')  + ' | [/COLOR]' + d.get('plot','')
					thumb_id = '$Teaser:' + id
					thumb_item = deep_get(item, 'images.aspect16x9')
					if not thumb_item:
						thumb_item = deep_get(item, 'images.aspect1x1')
					if not thumb_item:
						thumb_item = deep_get(item, 'images.aspect16x7')
					if thumb_item:
						thumb_src = thumb_item.get('src','')
						thumb_src = thumb_src.replace('{width}','1024')
						d['thumb'] = thumb_src
					d['_type'] = 'video'
					d['mode'] = 'libArdPlay'
					l.append(d)
	except:
		pass
	return l


def getVideoUrlHtml(url):
	response = libMediathek.getUrl(url)
	split = response.split('<script id="fetchedContextValue" type="application/json">');
	if (len(split) > 1):
		json_str = split[1]
		json_str = json_str.split('</script>')[0];
		j = json.loads(json_str)
		if isinstance(j, list):
			for listitem_outerlist in j:
				if isinstance(listitem_outerlist, list):
					for listitem_innerlist in listitem_outerlist:
						if isinstance(listitem_innerlist, dict):
							widgets = deep_get(listitem_innerlist, 'data.widgets')
							if widgets and isinstance(widgets, list):
								for widget in widgets:
									if widget.get('type',None) == 'player_ondemand':
										mediaCollection = deep_get(widget, 'mediaCollection.embedded.streams')
										if mediaCollection and isinstance(mediaCollection,list) and isinstance(mediaCollection[0],dict):
											return extractBestQuality(mediaCollection[0].get('media',[]), lambda x: None if isinstance(x,list) else x)
	return None


def extract(mediaCollection): 
	if mediaCollection and isinstance(mediaCollection,list) and isinstance(mediaCollection[0],dict):
		return extractBestQuality(mediaCollection[0].get('_mediaStreamArray',[]), lambda x: None if isinstance(x,list) else x)
	return None


def extractBestQuality(streams, fnGetFinalUrl):
	if streams:
		media = []
		for item in streams:
			if isinstance(item,dict) and (item.get('__typename','MediaStreamArray') == 'MediaStreamArray'):
				stream = item.get('url',None)
				if not stream:
					stream = item.get('_stream',None)
				if stream:
					url = fnGetFinalUrl(stream)
					if url:
						if url.startswith('//'):
							url = 'https:' + url
						quality = item.get('maxHResolutionPx',-1);
						if quality == -1:
							quality = item.get('_quality',-1);
						if (quality == 'auto') or item.get('isAdaptiveQualitySelectable',False):
							media.insert(0,{'url':url.replace("index.m3u8", "master.m3u8"), 'type':'video', 'stream':'hls'})
						elif url[-4:].lower() == '.mp4':
							try:
								quality = int(quality)
							except ValueError:
								pass
							else:
								media.append({'url':url, 'type':'video', 'stream':'mp4', 'bitrate':quality})
		ignore_adaptive = libMediathek.getSettingBool('ignore_adaptive')
		while ignore_adaptive and len(media) > 1 and media[0]['stream'] == 'hls':
			del media[0]
		if media:
			return dict(media = media)
	return None


def parse(pageIndex, url, partnerKey=None, channelKey=None, letter=None):
	result = []
	response = libMediathek.getUrl(url)
	page = json.loads(response)
	if page:
		widgets = page.get('channels' if pageIndex == pageIndexProgramPage else 'widgets',[])
		for widget in widgets:
			if (
				((channelKey is None) or (channelKey == widget.get('id' if pageIndex == pageIndexProgramPage else 'channelKey',None)))
				and 
				((letter is None) or (letter == widget.get('title',None)))
			):
				teasers = []
				if pageIndex == pageIndexProgramPage:
					teasers = [item for sublist in widget.get('timeSlots',(())) for item in sublist]
				elif (
					letter is not None 
					and 
					deep_get(widget, 'pagination.totalElements', 0) > deep_get(widget, 'pagination.pageSize', 0)
				):
					url = deep_get(widget, 'links.self.href')
					if url:
						url = url.split('?')[0]
						totalElements = deep_get(widget, 'pagination.totalElements')
						pageSize = deep_get(widget, 'pagination.pageSize')
						pageNumber = deep_get(widget, 'pagination.pageNumber',0)
						count = pageSize
						while count < totalElements:
							pageNumber = pageNumber + 1
							url2 = url + '?pageNumber=' + str(pageNumber) + '&pageSize=' + str(pageSize)
							response = libMediathek.getUrl(url2)
							widget2 = json.loads(response)
							teasers = teasers + widget2.get('teasers',[])
							count = count + pageSize  
				teasers = widget.get('teasers',[]) + teasers 
				for teaser in teasers:
					if teaser:
						type = teaser['type']
						publicationService = (widget if pageIndex == pageIndexProgramPage else teaser).get('publicationService',None)
						if (
						 	type in ('live','ondemand','broadcastMainClip','show','epg')
						 	and
							(type == 'live') == (pageIndex == pageIndexLivestreamPage)
							and
							(
								(partnerKey is None)
								or
								(
									publicationService
									and
									((channelKey if pageIndex == pageIndexProgramPage else partnerKey) == publicationService.get('partner',None))
								)
							)
						):
							documentId = deep_get(teaser, 'links.target.' + ('urlId' if pageIndex == pageIndexProgramPage else 'id'))
							if pageIndex == pageIndexProgramPage:
								name = teaser['coreTitle'] + ' | ' + teaser['title']
							else: 
								name = teaser['shortTitle']
							if documentId and name:
								d = {}
								d['documentId'] = documentId
								d['url'] = deep_get(teaser, 'links.target.href')
								if not d['url']:
									d['url'] = baseUrlDocuments + documentId
								d['name'] = name
								d['plot'] = (teaser if pageIndex == pageIndexProgramPage else page).get('synopsis', None)
								if not d['plot']:
									d['plot'] = teaser.get('longTitle',None)
								if pageIndex != pageIndexProgramPage:
									availableTo = teaser.get('availableTo',None)
									if availableTo and pageIndex != pageIndexLivestreamPage:
										d['plot'] = '[COLOR blue]' + addon.getLocalizedString(32013) + ' ' + libMediathek.str_to_airedtime(availableTo).strftime('%d.%m.%Y')  + ' | [/COLOR]' + d.get('plot','')
									broadcastedOn = teaser.get('broadcastedOn',None)
									if broadcastedOn and pageIndex != pageIndexLivestreamPage:
										d['plot'] = '[COLOR blue]' + addon.getLocalizedString(32012) + ' ' + libMediathek.str_to_airedtime(broadcastedOn).strftime('%d.%m.%Y')  + ' | [/COLOR]' + d.get('plot','')
								if (pageIndex in (pageIndexAZPage, pageIndexProgramPage)) and (partnerKey is None) and publicationService:
									d['name'] = d['name'] + ' | [COLOR blue]' + publicationService['name'] + '[/COLOR]'
								duration = teaser.get('duration', None)
								if duration:
									d['_duration'] = str(duration)
								thumb = deep_get(teaser, 'images.aspect16x9.src')
								if not thumb:
									thumb = deep_get(teaser, 'images.aspect1x1.src')
								if not thumb:
									thumb = deep_get(teaser, 'images.aspect16x7.src')
								if thumb:
									d['thumb'] = (thumb.split('?')[0]).replace('{width}','1024')
								if type == 'show':
									d['_type'] = 'dir'
									d['mode'] = 'libArdListShow'
								else:
									if pageIndex == pageIndexProgramPage:
										d['_airedISO8601'] = teaser.get('broadcastedOn', None)
									if pageIndex == pageIndexLivestreamPage:
										d['_type'] = 'live'
										d['live'] = 'true' 
									elif pageIndex == pageIndexProgramPage:
										d['_type'] = 'date'
									else:
										d['_type'] = 'video'
									d['mode'] = 'libArdPlay'
								result.append(d)
	# "Alle Sender nach Datum" ist nicht sinnvoll vorsortiert
	if pageIndex == pageIndexProgramPage and partnerKey is None:
		result.sort(key = lambda x: x.get('_airedISO8601',None))
	return result
