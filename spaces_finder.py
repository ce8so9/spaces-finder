#!/usr/bin/env python

# "Spaces finder" is a tool to quickly enumerate DigitalOcean Spaces to look for loot.
# It's similar to a subdomain bruteforcer but is made specifically to DigitalOcean
# Spaces and also has some extra features that allow you to grep for
# delicous files as well as download interesting files if you're not
# afraid to quickly fill up your hard drive.
# Built on top of AWSBucketDump by Jordan Potti(@ok_bye_now)

__author__ = "Bharath"
__twitter__ = "yamakira_"
__version__ = "0.0.1"

from argparse import ArgumentParser
import codecs
import requests
import xmltodict
import sys
import os
import shutil
import traceback
from queue import Queue
from threading import Thread, Lock

bucket_q = Queue()
download_q = Queue()

grep_list=None

arguments = None
total_public_spaces = 0

# Regions available for DigitalOcean Spaces - 'nyc3', 'ams3'
regions = ['nyc3', 'ams3', 'sgp1', 'sfo2', 'fra1']

def fetch(url):
    print('[+] fetching ' + url)
    try:
        response = requests.get(url)
    except requests.exceptions.RequestException as e:  # This is the correct syntax
        print(e)
        sys.exit(1)
    if response.status_code == 403 or response.status_code == 404:
        status403(url)
    if response.status_code == 200:
        if "Content" in response.text:
            returnedList=status200(response,grep_list,url)

def bucket_worker():
    while True:
        item = bucket_q.get()
        try:
            fetch(item)
        except Exception as e:
            traceback.print_exc(file=sys.stdout)
            print(e)
        bucket_q.task_done()

def downloadWorker():
    print('[+] download worker running')
    while True:
        item = download_q.get()
        try:
            downloadFile(item)
        except Exception as e:
            traceback.print_exc(file=sys.stdout)
            print(e)
        download_q.task_done()
directory_lock = Lock()

def get_directory_lock():
    directory_lock.acquire()

def release_directory_lock():
    directory_lock.release()

def get_make_directory_return_filename_path(url):
    global arguments
    bits = url.split('/')
    directory = arguments.savedir
    for i in range(2,len(bits)-1):
        directory = os.path.join(directory, bits[i])
    try:
        get_directory_lock()
        if not os.path.isdir(directory):
            os.makedirs(directory)
    except Exception as e:
        traceback.print_exc(file=sys.stdout)
        print(e)
    finally:
        release_directory_lock()

    return os.path.join(directory, bits[-1]).rstrip()

interesting_file_lock = Lock()
def get_interesting_file_lock():
    interesting_file_lock.acquire()

def release_interesting_file_lock():
    interesting_file_lock.release()

def write_interesting_file(filepath):
    try:
        get_interesting_file_lock()
        with open('interesting_file.txt', 'ab+') as interesting_file:
            interesting_file.write(filepath.encode('utf-8'))
            interesting_file.write('\n'.encode('utf-8'))
    finally:
        release_interesting_file_lock()

def downloadFile(filename):
    global arguments
    print('[+] Downloading {}'.format(filename))
    local_path = get_make_directory_return_filename_path(filename)
    local_filename = (filename.split('/')[-1]).rstrip()
    print('[*] local {}'.format(local_path))
    if local_filename =="":
        print("Directory..\n")
    else:
        r = requests.get(filename.rstrip(), stream=True)
        if 'Content-Length' in r.headers:
            if int(r.headers['Content-Length']) > arguments.maxsize:
                print("[!] This file is greater than the specified max size.. skipping..\n")
            else:
                with open(local_path, 'wb') as f:
                    shutil.copyfileobj(r.raw, f)
        r.close()

def print_banner():
        print('''\nDescription:
        "Spaces finder" is a tool to quickly enumerate DigitalOcean Spaces to look for loot.
        It's similar to a subdomain bruteforcer but is made specifically to DigitalOcean Spaces
        and also has some extra features that allow you to grep for
        delicous files as well as download interesting files if you're not
        afraid to quickly fill up your hard drive.

        by yamakira_
        '''
        )   

def cleanup():
   print("[-] Cleaning Up Files")

def public_spaces_count():
    print("\033[1;32m[*] Total number of public Spaces found - {}\033[1;m".format(total_public_spaces))

def status403(line):
    print("[!]" + line.rstrip() + " is not accessible")

def queue_up_download(filepath):
    download_q.put(filepath)
    print('[*] Collectable: {}'.format(filepath))
    write_interesting_file(filepath)

def status200(response,grep_list,line):
    global total_public_spaces
    total_public_spaces += 1
    print("\033[1;31m[*] {} is publicly accessible\033[1;m".format(line.rstrip()))
    print("[+] Pilfering "+line.rstrip())
    objects=xmltodict.parse(response.text)
    Keys = []
    interest=[]
    try:
        for child in objects['ListBucketResult']['Contents']:
            Keys.append(child['Key'])
    except:
        pass
    hit = False
    for words in Keys:
        words = (str(words)).rstrip()
        collectable = line+'/'+words
        if grep_list != None and len(grep_list) > 0:
            for grep_line in grep_list:
                grep_line = (str(grep_line)).rstrip()
                if grep_line in words:
                    queue_up_download(collectable)
                    break
        else:
            queue_up_download(collectable)
    return total_public_spaces

def main():
    global arguments
    global grep_list
    parser = ArgumentParser()
    parser.add_argument("-D", dest="download", required=False, action="store_true", default=False, help="Download files. This requires significant diskspace") 
    parser.add_argument("-d", dest="savedir", required=False, default='', help="if -D, then -d 1 to create save directories for each space with results.")
    parser.add_argument("-l", dest="hostlist", required=True, help="") 
    parser.add_argument("-g", dest="grepwords", required=False, help="Provide a wordlist to grep for")
    parser.add_argument("-m", dest="maxsize", type=int, required=False, default=1024, help="Maximum file size to download.")
    parser.add_argument("-t", dest="threads", type=int, required=False, default=1, help="thread count.")

    if len(sys.argv) == 1:
        print_banner()
        parser.error("[!] No arguments given.")
        parser.print_usage
        sys.exit()

    # output parsed arguments into a usable object
    arguments = parser.parse_args()

    # specify primary variables
    with open(arguments.grepwords, "r") as grep_file:
        grep_content = grep_file.readlines()
    grep_list = [ g.strip() for g in grep_content ]

    if arguments.download and arguments.savedir:
        print("[*] Downloads enabled (-D), and save directories (-d) for each host will be created/used")
    elif arguments.download and not arguments.savedir:
        print("[*] Downloads enabled (-D), and will be saved to current directory")
    else:
        print("[*] Downloads were not enabled (-D), not saving results locally.")

    # start up bucket workers
    for i in range(0,arguments.threads):
        print('[+] starting thread')
        t = Thread(target=bucket_worker)
        t.daemon = True
        t.start()
       
    # start download workers 
    for i in range(1, arguments.threads):
        t = Thread(target=downloadWorker)
        t.daemon = True
        t.start()

    with open(arguments.hostlist) as f:
        for line in f:
            for region in regions:
                bucket = 'https://'+line.rstrip()+'.'+region+'.digitaloceanspaces.com'
                print('[+] queuing {}'.format(bucket))
                bucket_q.put(bucket)

    bucket_q.join()
    if arguments.download:
        download_q.join()

    public_spaces_count()
    cleanup()

if __name__ == "__main__":
    main()

