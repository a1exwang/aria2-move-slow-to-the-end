import aria2p
from pprint import pprint
import time
from datetime import datetime
from datetime import timedelta
import requests
import sys


if len(sys.argv) != 3:
    print('invalid arguments')
    exit(1)

host, port = sys.argv[1], int(sys.argv[2])
max_inactive_time = timedelta(hours=1)
update_interval_seconds = 10

def move_task_end(aria2, client, download):

    # Pause the task
    while True:
        result = aria2.get_download(download.gid)
        print('task %s status %s' % (download.gid, result.status))
        if result.status == 'paused':
            print('paused %s' % download.gid)
            break

        print('trying to pause %s' % download.gid)
        try:
            client.pause(download.gid)
        except Exception as e:
            if 'cannot be paused now' in str(e):
                print('cannot be paused now, retry later')
                time.sleep(1)

            else:
                raise e
        time.sleep(1)
    print('pausing the task %s successfully' % (download.gid))

    while True:
        result = aria2.get_download(download.gid)
        if result.status != 'paused':
            print('unpaused %s, currently %s' % (download.gid, result.status))
            break

        print('trying to unpause %s' % download.gid)
        try:
            client.unpause(download.gid)
        except Exception as e:
            if 'cannot be unpaused now' in str(e):
                print('cannot be unpaused now, retry later')
                time.sleep(1)
            else:
                raise e
        time.sleep(1)
    print('unpausing the task %s successfully' % (download.gid,))
    
    while True:
        print('trying to move %s the the end' % download.gid)

        last_waiting = None
        for d1 in aria2.get_downloads():
            if d1.status == 'waiting':
                last_waiting = d1
            if d1.gid == download.gid and d1.status == 'active':
                print('while moving task %s to the end, the task becomes active' % download.gid)
                break

        if last_waiting and last_waiting.gid == download.gid:
            print('moved task %s to the end of the queue' % download.gid)
            break

        client.change_position(download.gid, 1, 'POS_END')

def main_loop(host, port, update_interval_seconds, max_inactive_time):
    client = aria2p.Client(
            host=host,
            port=port,
            secret="",)
    aria2 = aria2p.API(client)

    # main loop
    tasks_active = {}
    while True:
        now = datetime.now()
        tasks_active_new = {}
        downloads = aria2.get_downloads()

        # Report status
        stats = {'waiting': 0, 'active': 0, 'seeding': 0, 'complete': 0}
        for download in downloads:
            if download.status == 'waiting':
                stats['waiting'] += 1
            elif download.status == 'complete':
                if not download.followed_by:
                    stats['complete'] += 1
            elif download.status == 'active':
                if download.completed_length >= download.total_length and download.total_length > 0:
                    stats['seeding'] += 1
                else:
                    stats['active'] += 1

                    # update 'added_time'
                    if download.gid in tasks_active:
                        tasks_active_new[download.gid] = {'raw': download, 'added_time': tasks_active[download.gid]['added_time'], 'last_download_active_time': tasks_active[download.gid]['last_download_active_time']}
                    else:
                        tasks_active_new[download.gid] = {'raw': download, 'added_time': now, 'last_download_active_time': now}

                    # update 'download_active_time'
                    if download.download_speed > 0:
                        tasks_active_new[download.gid]['last_download_active_time'] = now
        tasks_active = tasks_active_new

        # Move 'inactive downloading tasks' to the end of the queue
        for gid in tasks_active:
            t = tasks_active[gid]
            inactive_time = now - t['last_download_active_time']
            print("Task %s, Inactive time: %s" % (gid, inactive_time))
            if inactive_time > max_inactive_time:
                print("Task %s, move to the end of the queue" % gid)
                # Only move one task at time
                move_task_end(aria2, client, tasks_active[gid]['raw'])
                break

        # Make sure no task is paused
        print(client.call('aria2.unpauseAll'))
        
        print('Active: %d, Waiting: %d, Seeding %d, Complete %d' % (stats['active'], stats['waiting'], stats['seeding'], stats['complete']))
        # wait a moment
        time.sleep(update_interval_seconds)

while True:
    try:
        main_loop(host, port, update_interval_seconds, max_inactive_time)
    except requests.exceptions.ConnectionError as e:
        print("Networking down, retrying...")
        time.sleep(1)
