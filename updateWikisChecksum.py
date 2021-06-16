import hashlib
import json
import requests
import pandas as pd

endpoints = [
    {
        "wiki": {
            "url": "http://organicdatacuration.org/enigma_dev/api.php",
            "username": "_YOUR_BOT_",
            "password": "_BOT_PASSWORD_"
        },
        "sparql": {
            "url": "_SPARQL_ENDPOINT_",
            "username": "",
            "password": ""
        }
    },
]

class SessionWithUrlBase(requests.Session):
    def __init__(self, url_base=None, *args, **kwargs):
        super(SessionWithUrlBase, self).__init__(*args, **kwargs)
        self.url_base = url_base

    def request(self, method, url, **kwargs):
        modified_url = self.url_base + url
        return super(SessionWithUrlBase, self).request(method, modified_url, **kwargs)


def check_all_files (generalConf):
    #Create sessions:
    sparqlSession = createSparqlSession(generalConf["sparql"])
    botSession = createWikiBotSession(generalConf["wiki"])

    tkn = getCSRFToken(botSession)
    updateChecksum = getUpdateChecksumF(botSession, tkn)

    wikiEntries = getAllFiles(sparqlSession)
    for entry in wikiEntries:
        nHash = getExternalFileHash(entry["file"])
        if (nHash != entry["hash"]):
            pagename = entry["page"].split("/")[-1]
            print(pagename + " has a new hash: " + nHash)
            updateChecksum(pagename, nHash)
        else:
            print(entry["page"] + " old hash is still valid")
        break

def createSparqlSession (conf):
    sparqlSession = SessionWithUrlBase(url_base=conf["url"])
    sparqlSession.auth = (conf["username"] , conf["password"])
    return sparqlSession

def createWikiBotSession (conf):
    botSession = SessionWithUrlBase(url_base=conf["url"])
    # First we need to retrieve login token
    PARAMS_TOKEN = {
        'action':"query",
        'meta':"tokens",
        'type':"login",
        'format':"json"
    }
    loginTokenRes = botSession.get("", params=PARAMS_TOKEN).json()
    LOGIN_TOKEN = loginTokenRes['query']['tokens']['logintoken']
    print("Login Token: ",LOGIN_TOKEN)

    # Go to http://organicdatacuration.org/enigma_new/index.php/Special:BotPasswords for lgname & lgpassword, and add them below
    PARAMS_LOGIN = {
        'action': "login",
        'lgname': conf["username"],
        'lgpassword': conf["password"],
        'lgtoken': LOGIN_TOKEN,
        'format': "json"
    }

    loginReq = botSession.post("", data=PARAMS_LOGIN).json()
    print(loginReq)
    return botSession

def getAllFiles (sparql):
    query = "PREFIX enigma: <https://w3id.org/enigma#>"\
          + "SELECT ?page ?file ?hash WHERE {"\
          + "  ?page enigma:hasContentUrl ?file ."\
          + "  optional {?page enigma:checksum ?hash}"\
          + "} ORDER BY ?page"

    response = sparql.post("", data = {'query': query})
    res = json.loads(response.text)

    query_results=[]
    for item in res['results']['bindings']:
        entry = {} 
        entry["page"] = item["page"]["value"] if ("page" in item) else None
        entry["file"] = item["file"]["value"] if ("file" in item) else None
        entry["hash"] = item["hash"]["value"] if ("hash" in item) else None
        query_results.append(entry)
    
    return query_results

def getExternalFileHash (fileurl):
    #Get the file
    sha = hashlib.sha1()
    try:
        with requests.get(fileurl, stream=True) as r:
            r.raise_for_status()
            for chunk in r.iter_content(chunk_size=8192): 
                sha.update(chunk)

        digest = sha.hexdigest()
        return digest
    except:
        print("Error downloading " + fileurl)
        return None

def getCSRFToken (session):
    PARAMS_CSRFT = {
        "action": "query",
        "meta": "tokens",
        "format": "json"
    }

    response = session.get("", params=PARAMS_CSRFT)
    DATA = response.json()
    return DATA['query']['tokens']['csrftoken']

def getUpdateChecksumF (session, token):
    def _getEditParams(page, append):
        return {
            "action": "edit",
            "title": page,
            "section": "new",
            "format": "json",
            "text": append,
            "token": token
        }
    def _updateChecksum(page, checksum):
        text_to_append="{{#set:|Checksum (E)="+checksum+"}}" #FIXME: this ADDs a checksum, does not update!
        req = session.post("", data=_getEditParams(page, text_to_append))
        data = req.json()
        print(page + " updated!")
    return _updateChecksum

check_all_files(endpoints[0])
