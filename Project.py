#!/Users/$USERNAME/anaconda/bin/python
# -*- coding: UTF8 -*-

from __future__ import division
import re
import itertools
import math
import _mysql as MyS
import nltk
from nltk.tokenize import RegexpTokenizer
from urllib2 import *
import sys
from snownlp import SnowNLP
from nltk.corpus import wordnet as wn
from microsofttranslator import Translator

#connection to MySQL database
conn = MyS.connect(unix_socket='/Applications/MAMP/tmp/mysql/mysql.sock',user='root', passwd='root', port =8889, host='localhost', db='project_db')
#connection to Microsoft Translator
translator = Translator('project_translate', '***key for translator***')


range1 = sys.argv[1]
range2 = sys.argv[2]
docRange = sys.argv[3]
hskLevel = sys.argv[4]
userTopics = sys.argv[5]


charQuery = """SELECT * FROM """ + hskLevel
topicQuery = """SELECT * FROM SnowNLP""" + userTopics


#get user characters from database
def query1(charQuery):
	characters=""
	conn.query(charQuery)
	result = conn.store_result()
	while(result.fetch_row()):
		for row in result.fetch_row():
			characters += row[0]
	return characters

#get user topics from database
def query2(topicQuery):
	topics=""
	conn.query(topicQuery)
	result = conn.store_result()
	while(result.fetch_row()):
		for row in result.fetch_row():
			topics += row[1] + ","
	return topics

queryString=query1(charQuery)
userTopic=query2(topicQuery)

conn.close()


def tokenize(userTopic):
    #split the user topic string into separate words
    tokenizer = RegexpTokenizer(r'\w+')
    #the user's topic list
    engTopics = tokenizer.tokenize(userTopic)
    return engTopics

engTopics = tokenize(userTopic)



#lists for english and chinese synonyms
engSynList = []
chiSynList = []

#function for stripping English wordNet search result.
def wnSynonym():
    #define regular expression for extracting word from synonym result
    reg_exp = re.compile(r"'\b\w+\.")
    #return topic synonyms from WordNet
    synonymList = [wn.synsets(topic) for topic in engTopics]
    #extract word from result
    regExpResult = [re.findall(reg_exp, str(synonym)) for synonym in synonymList]
    #merge all to one list
    allSynonyms = list(itertools.chain.from_iterable(regExpResult))
    #remove duplicate words
    setSynonyms = set(allSynonyms)
    #remove punctation from beginning and end of word
    engSynList = [word[1:-1] for word in setSynonyms]
    #format wordnet result for use
    engSynList = [engSyn.replace("_", " ") for engSyn in engSynList]
    return engSynList

#function for translating english topics to chinese
def translateTopic(wnSynonym, args):
    #get synonym list
    engSynList = wnSynonym()
    #create query string for translation
    queryString = ','.join(engSynList)
    chiSyn = translator.translate(queryString, 'zh-CHS')
    #encode to utf8 for string conversion
    chiSyn = chiSyn.encode('utf8')
    #split by delimiter, all possible commas.
    pattern = re.compile(r",|，|、| ，")
    chiSynList = pattern.split(chiSyn)
    #no repeated words
    return set(chiSynList)

#user topics translated to Chinese
chineseTopics = translateTopic(wnSynonym,())


#preparing query string for http
def editQuery(queryString):
    #encoding
    queryDecode = queryString.decode('utf-8')
    queryObj = SnowNLP(queryDecode)
    #split the user query string to separate words
    queryWordList = set(queryObj.words)
    #split query by commas
    tokenQuery= ",".join(queryWordList).encode('utf8')
    return (tokenQuery, queryWordList)



#urllib.quote to create ASCII string for http query
tokenQuery, queryWordList = editQuery(queryString)
newString = quote(tokenQuery)

#query Solr via http
solrReader = urlopen('http://localhost:8983/solr/collection2/select?q=' + newString + '&rows='+docRange+'&fq=wordcount%3A%5B' + range1 + '+TO+' + range2 + '%5D&sort=score+desc&wt=json&indent=true')


SolrResponse = eval(solrReader.read().decode('utf-8'))

def returnResult(SolrResponse):
    #read the Solr query result
    for doc in SolrResponse['response']['docs']:
        id = doc['id']
        article = doc['text'][0].decode('utf8')
        #strip whitespace
        article = ''.join(article.split())
        #make article SnowNLP object
        articleObj = SnowNLP(article)
        # get all words in article
        docWordList = articleObj.words
        #10 keywords of the text
        articleKeyWords = articleObj.keywords(10)
        #amount of topics in common
        topicCount = len(set(chineseTopics) & set(articleKeyWords))
        #ratio of topics in doc to topics in user database
        topicRatio =  topicCount / len(chineseTopics)
        #bias for ranking equation
        bias = 0.1
        #number of words in doc that are known to the user
        wordsInCommon = len(set(queryWordList) & set(docWordList))
        #number of unique words in document
        articleMinusRepeat = len(set(docWordList))
        #percentage of document that is comprised of user's known words
        percentage = round(  ( ( wordsInCommon/articleMinusRepeat)* 100),2 )
        #word ratio for ranking equation
        ratioMatchedChars = wordsInCommon/articleMinusRepeat
        #ranking equation
        finalScore = ((1.0-bias) * (topicRatio)) + ((bias) * ratioMatchedChars)
        #return to PHP script
        print '&&&'.join(map(str, (percentage, id, article[0:200].encode('utf8'), wordsInCommon, finalScore, articleMinusRepeat)))



returnResult(SolrResponse)



solrReader.close()
