#!/usr/bin/env python3

import glob
import subprocess
import os
import sys
import io
import time
import hashlib
import json
import zipfile

#needs to be equal or smaller than the cron
period = 300
outputDir = "share/locale/"
s3Urls = ["s3://extensions.musescore.org/4.0/languages/"]

def processTsFile(prefix, langCode, data):
    print(f"Processing {langCode}")
    filename = f'{prefix}_{lang_code}'
    tsFilePath = outputDir + filename + ".ts"
    qmFilePath = outputDir + filename + ".qm"

    lang_time = int(os.path.getmtime(tsFilePath))
    cur_time = int(time.time())
    #print(cur_time,lang_time,cur_time-lang_time)

    # if the file has been updated, update or add entry in details.json
    if (cur_time - lang_time < period) or not os.path.isfile(qmFilePath):
        # generate qm file
        lrelease = subprocess.Popen(['lrelease', tsFilePath, '-qm', qmFilePath])
        lrelease.communicate()

        # get qm file size
        file_size = os.path.getsize(qmFilePath)
        file_size = "%.2f" % (file_size / 1024)

        with open(qmFilePath, 'rb') as file:
            hash_file = hashlib.sha1()
            hash_file.update(file.read())
        if lang_code not in data:
            data[lang_code] = {}
        if prefix not in data[lang_code]:
            data[lang_code][prefix] = {}

        data[lang_code][prefix]["file_name"] = f"{filename}.qm"
        data[lang_code][prefix]["hash"] = str(hash_file.hexdigest())
        data[lang_code][prefix]["file_size"] = file_size

        return True
    else:
        print(f'{prefix} {lang_code} not changed')
        return False


newDetailsFile = False
translationChanged = False

with open("share/locale/languages.json", "r+") as langCode_file:
    langCodeNameDict = json.load(langCode_file)  # language code --> name
detailsJson = f"{outputDir}details.json"
# read details.json or create it
if os.path.isfile(detailsJson):
    with open(f"{outputDir}details.json", "r+") as json_file:
        data = json.load(json_file)
else:
    newDetailsFile = True
    data = {"type": "Languages", "version": "2.0"}
translationChanged = newDetailsFile
for lang_code, languageName in langCodeNameDict.items():
    updateMscore = processTsFile("musescore", lang_code, data)
    translationChanged = updateMscore or translationChanged

    updateInstruments = processTsFile("instruments", lang_code, data)
    translationChanged = updateInstruments or translationChanged

    if (updateMscore or updateInstruments):
        #create a zip file, compute size, hash, add it to json and save to s3
        zipName = f'locale_{lang_code}.zip'
        zipPath = outputDir + zipName
        myzip = zipfile.ZipFile(zipPath, mode='w')
        qmFilePath = f'{outputDir}musescore_{lang_code}.qm'
        myzip.write(qmFilePath, f'musescore_{lang_code}.qm')
        qmFilePath = f'{outputDir}instruments_{lang_code}.qm'
        myzip.write(qmFilePath, f'instruments_{lang_code}.qm')
        myzip.close()

        # get zip file size
        file_size = os.path.getsize(zipPath)
        file_size = "%.2f" % (file_size / 1024)

        with open(zipPath, 'rb') as file:
            hash_file = hashlib.sha1()
            hash_file.update(file.read())
        data[lang_code]["file_name"] = zipName
        data[lang_code]["name"] = langCodeNameDict[lang_code]
        data[lang_code]["hash"] = str(hash_file.hexdigest())
        data[lang_code]["file_size"] = file_size
        for s3Url in s3Urls:
            push_zip = subprocess.Popen(['s3cmd','put', '--acl-public', '--guess-mime-type', zipPath, s3Url + zipName])
            push_zip.communicate()


with open(f"{outputDir}details.json", "w") as json_file:
    json_file.write(json.dumps(data, sort_keys=True, indent=4))
if translationChanged:
    for s3Url in s3Urls:
        push_json = subprocess.Popen(
            [
                's3cmd',
                'put',
                '--acl-public',
                '--guess-mime-type',
                f'{outputDir}details.json',
                f'{s3Url}details.json',
            ]
        )
        push_json.communicate()


