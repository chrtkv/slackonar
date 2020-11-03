#! /usr/bin/env python3
import datetime
import json
import logging
import os
import re
import sys
import urllib.parse

import requests
from requests_toolbelt.multipart.encoder import MultipartEncoder


def get_crumb():
    headers = {
        'user-agent': "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/77.0.3865.90 Safari/537.36",
    }
    # get the login form text for crumb parsing
    form_text = requests.get(WORKSPACE_URL, headers=headers).text
    # search the crumb string
    crumb_string = re.search("(?<=crumbValue&quot;:&quot;)(.*?)&quot;", form_text).group(1)
    # urlencode it
    crumb = urllib.parse.quote(crumb_string).replace("-%5Cu2603", "-%E2%98%83")
    return crumb


def get_cookie():
    payload = "signin=1&crumb={}&email={}&password={}".format(CRUMB, USER, PASSWORD)
    headers = {
        'content-type': "application/x-www-form-urlencoded",
        'user-agent': "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/77.0.3865.90 Safari/537.36"
    }
    response = requests.post(WORKSPACE_URL, data=payload, headers=headers, allow_redirects=False)

    for cookie in re.split(' ', response.headers['Set-Cookie']):
        if "d=" in cookie:
            return cookie


def get_token():
    url = "https://app.slack.com/auth?app=client"

    headers = {
        'cookie': COOKIE
    }

    auth = requests.get(url, headers=headers)
    auth_data = re.search(r'stringify\((.*)\);\n', auth.text).group(1)
    auth_data_json = json.loads(auth_data)
    teams = auth_data_json['teams']

    for team in teams:
        team_info = teams[team]
    return team_info['token']


def get_messages(channel_id, first_message_time, last_message_time):
    url = "{}/api/conversations.history".format(WORKSPACE_URL)

    multipart_data = MultipartEncoder(
        fields={
            'channel': channel_id,
            'limit': '1000',
            'token': TOKEN,
            'oldest': f'{first_message_time[:10]}',
            'latest': f'{int(last_message_time[:10]) + 1}',
        }
    )

    headers = {
        "Content-Type": multipart_data.content_type,
        'cookie': COOKIE,
    }

    get_msgs = requests.post(url, data=multipart_data, headers=headers, verify=False)
    messages = get_msgs.json()["messages"]

    return messages


def get_messages_from_thread(channel_id, thread_id, replies):
    url = '{}/api/conversations.replies'.format(WORKSPACE_URL)
    # messages limit
    limit = replies

    data = "channel={}&ts={}&limit={}&token={}".format(channel_id, thread_id, limit, TOKEN)
    
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        'cookie': COOKIE
    }

    thread = requests.get(url, headers=headers, params=data)

    return thread.json()


def get_user_info_by_id(user_id):
    url = '{}/api/users.profile.get'.format(WORKSPACE_URL)

    data = "user={}&token={}".format(user_id, TOKEN)
    
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        'cookie': COOKIE
    }

    user_info = requests.get(url, headers=headers, params=data)

    return user_info.json()


def id2name(matchobj):
    id = re.sub(r'[\W_]+', '', matchobj.group(0))
    return f"_{get_user_info_by_id(id)['profile']['real_name']}_"


def formatter(message):
    # get message author name
    name = get_user_info_by_id(message['user'])['profile']['real_name']
    # check if message contain only technical info
    if 'subtype' in message.keys():
        return
    # fix markdown sintax for correct pdf rendering
    message_text = re.sub('```', '\n```\n', message['text'])
    # replace id in mentions to user names
    message_text = re.sub('<@[A-Z0-9]{11}>', id2name, message_text)
    # replace &gt; to angle bracket
    message_text = re.sub('&gt;', '>', message_text)
    # convert hyperlinks to markdown format
    if re.search(r'(?<=\<)(.*)\|(.*)(?<!\>)\>', message_text) is not None:
        url = re.search(r'(?<=\<)(.*)\|(.*)(?<!\>)\>', message_text).group(1)
        text = re.search(r'(?<=\<)(.*)\|(.*)(?<!\>)\>', message_text).group(2)
        link = f'[{text}]({url})'
        message_text = re.sub(r'\<(?<=\<)(.*)\|(.*)(?<!\>)\>', link, message_text)
    # add images
    if 'files' in message.keys():
        image_urls = []
        for file in message['files']:
            if 'mimetype' in file.keys():
                if 'image' in file['mimetype']:
                    image_urls.append(file["url_private"])
        for url in image_urls:
            filename = download_image(url)
            message_text = f'{message_text}\n\n![](images/{filename})'
    # add name and indent, if message is a part of thread
    if 'parent_user_id' in message.keys():
        message_text = message_text.replace('\n', '\n> ')
        message_text = f'\n> **{name}**: {message_text}\n'
    else:
        message_text = f'\n**{name}**: {message_text}\n'
    return message_text


def download_image(url):
    headers = {
        'cookie': COOKIE
    }
    for _attempt in range(100):
        try:
            request = requests.get(url, headers=headers, allow_redirects=True, timeout=1)
        except requests.exceptions.Timeout:
            continue
        break
    filename = url.split('/')[-2]
    extension = url.split('.')[-1]
    if request.status_code == 200:
        with open(f'/slackonar/slackonars/images/{filename}.{extension}', 'wb') as file:
            file.write(request.content)
    return f'{filename}.{extension}'


if __name__ == "__main__":
    # hide warnings about certificate verification
    logging.captureWarnings(True)

    # create dirs
    os.makedirs('/slackonar/slackonars/images', exist_ok=True)


    first_message_url = sys.argv[1].split('/')
    workspace = first_message_url[2]
    channel_id = first_message_url[4]
    message_id = first_message_url[5]
    first_message_time = re.search('p([0-9].*)', message_id).group(1)
    last_message_time = '1800000000'
    if len(sys.argv) > 2:
        last_message_url = sys.argv[2].split('/')
        last_message_time = re.search('p([0-9].*)', last_message_url[5]).group(1)

    USER = os.environ['EMAIL']
    PASSWORD = os.environ['PASSWORD']
    WORKSPACE_URL = f'https://{workspace}'
    CRUMB = get_crumb()
    COOKIE = get_cookie()
    TOKEN = get_token()

    filename = f"{'{:%d.%m.%Y-%H:%M:%S}'.format(datetime.datetime.now())}.md"
    for message in reversed(get_messages(channel_id, first_message_time, last_message_time)):
        # for messages with thread
        if 'thread_ts' and 'reply_count' in message.keys():
            thread = (get_messages_from_thread(channel_id, message['thread_ts'], message['reply_count']))
            for thread_message in thread['messages']:
                with open(f'/slackonar/slackonars/{filename}', 'a+') as file:
                    file.write(f'{formatter(thread_message)}')
        # for messages without thread
        else:
            formatted_message = formatter(message)
            if formatted_message:
                with open(f'/slackonar/slackonars/{filename}', 'a+') as file:
                    file.write(formatted_message)
