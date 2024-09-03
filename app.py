import httpx
import logging
import time
import random
import csv
import threading
from instagrapi import Client
from instagrapi.exceptions import TwoFactorRequired, ClientError, PrivateError
from datetime import datetime
from typing import List, Optional, Union

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Define the account details
ACCOUNTS = [
    {
        "ig_username": "jafarjafar123345",
        "ig_password": "EmviNQ0Vcumm"
    }
]

# Define the range for the delay in seconds
MIN_DELAY = 600  # 10 minutes
MAX_DELAY = 1200  # 20 minutes

# URL of the image to send
IMAGE_URL = "https://i.kym-cdn.com/photos/images/original/002/733/202/719.jpg"
IMAGE_PATH = "downloaded_image.jpg"

# Define the global messages for split testing
GLOBAL_MESSAGES = [
    "Shockingly shameful to start any convo this way but if I could get you 30 gym members in the door within 1 month & you'd only pay per signed member without wasting time studying marketing, would you be interested in a partnership?",
    "If I could get you 30 gym members in the door within 1 month & you'd only pay per signed member without wasting time studying marketing, would you be interested in a partnership?"
]

def download_image(url, path):
    with httpx.Client() as client:
        response = client.get(url)
        if response.status_code == 200:
            with open(path, 'wb') as file:
                file.write(response.content)
            logger.info(f"Image downloaded to {path}")
        else:
            logger.error(f"Failed to download image from {url}")

def consent_required_flow_1(client):
    return client.private_request(
        "consent/existing_user_flow/",
        data={
            "_uid": client.user_id,
            "_uuid": client.uuid,
        }
    )

def consent_required_flow_2(client):
    return client.private_request(
        "consent/existing_user_flow/",
        data={
            "current_screen_key": "qp_intro",
            "_uid": client.user_id,
            "_uuid": client.uuid,
            "updates": '{"existing_user_intro_state":"2"}'
        }
    )

def consent_required_flow_3(client):
    return client.private_request(
        "consent/existing_user_flow/",
        data={
            "current_screen_key": "tos_and_two_age_button",
            "_uid": client.user_id,
            "_uuid": client.uuid,
            "updates": '{"age_consent_state":"2","tos_data_policy_consent_state":"2"}'
        }
    )

def handle_consent_required(client):
    consent_required_flow_1(client)
    consent_required_flow_2(client)
    consent_required_flow_3(client)

def login(ig_username, ig_password):
    client = Client()
    try:
        client.login(ig_username, ig_password)
        logger.info(f"Logged in as {ig_username}")
        return client
    except TwoFactorRequired:
        logger.info(f"Two-factor authentication required for {ig_username}.")
        two_factor_code = input(f"Enter the 2FA code for {ig_username}: ")
        client.two_factor_login(ig_username, ig_password, two_factor_code)
        logger.info(f"Logged in as {ig_username} with 2FA")
        return client
    except PrivateError as e:
        if 'consent_required' in str(e):
            logger.error(f"Consent required for {ig_username}. Handling consent...")
            handle_consent_required(client)
            client.login(ig_username, ig_password)
            logger.info(f"Logged in as {ig_username} after consent")
            return client
        else:
            logger.error(f"Login failed for {ig_username}: {e}")
    except ClientError as e:
        logger.error(f"Client error occurred for {ig_username}: {e}")
    except Exception as e:
        logger.error(f"An unexpected error occurred for {ig_username}: {e}")

def send_dm(client, username, message):
    try:
        if conversation_exists(client, username):
            logger.info(f"Conversation already exists with {username}. Skipping DM.")
            return None
        user_id = client.user_id_from_username(username)
        dm_id = client.direct_send(message, [user_id])
        logger.info(f"Message sent to {username} with ID: {dm_id}")
        photo_dm_id = client.direct_send_photo(IMAGE_PATH, [user_id])
        logger.info(f"Photo sent to {username} with ID: {photo_dm_id}")
        return {'thread_id': dm_id.thread_id, 'message_type': message}
    except ClientError as e:
        logger.error(f"Failed to send DM to {username}: {e}")
        return None

def generate_random_delay(min_delay, max_delay):
    mean = (min_delay + max_delay) / 2
    std_dev = (max_delay - min_delay) / 6
    delay = random.gauss(mean, std_dev)
    return max(min_delay, min(max_delay, delay))

def track_responses(client, sent_messages):
    while True:
        command = input("Enter 'check' to check response rates or 'quit' to exit: ")
        if command.lower() == 'check':
            total_messages = len(sent_messages)
            responded_messages = {}
            for message_type in GLOBAL_MESSAGES:
                responded_messages[message_type] = 0
            for dm_info in sent_messages:
                thread_id = dm_info['thread_id']
                message_type = dm_info['message_type']
                try:
                    thread = client.direct_threads(thread_id)
                    if thread and thread[0].messages:
                        last_message = thread[0].messages[-1]
                        if last_message.user_id != client.user_id:
                            responded_messages[message_type] += 1
                except ClientError as e:
                    logger.error(f"Error retrieving thread {thread_id}: {e}")
                    continue
            logger.info("Response Rates:")
            for message_type, count in responded_messages.items():
                total_messages_of_type = sum(1 for dm_info in sent_messages if dm_info['message_type'] == message_type)
                response_rate = (count / total_messages_of_type) * 100 if total_messages_of_type > 0 else 0
                logger.info(f"{message_type}: {response_rate:.2f}%")
        elif command.lower() == 'quit':
            break
        else:
            logger.info("Invalid command. Please try again.")

def read_users_from_csv(file_path):
    users = []
    with open(file_path, newline='') as csvfile:
        reader = csv.reader(csvfile)
        for row in reader:
            if row:
                users.append(row[0].strip())
    return users

def send_messages_from_account(account, users, batch_size):
    client = login(account['ig_username'], account['ig_password'])
    if not client:
        return
    sent_messages = []
    for i in range(0, len(users), batch_size):
        batch = users[i:i + batch_size]
        for user in batch:
            message = random.choice(GLOBAL_MESSAGES)
            dm_info = send_dm(client, user, message)
            if dm_info:
                sent_messages.append(dm_info)
            if len(sent_messages) % 5 == 0:
                logger.info("Reached 5 messages, recalculating total delay to align with hourly schedule...")
                time_to_wait = 3600 - sum(generate_random_delay(MIN_DELAY, MAX_DELAY) for _ in range(5))
                time.sleep(max(time_to_wait, 0))
            else:
                delay = generate_random_delay(MIN_DELAY, MAX_DELAY)
                logger.info(f"Waiting for {delay:.2f} seconds before sending the next message...")
                time.sleep(delay)
    track_responses(client, sent_messages)

def conversation_exists(client, username):
    user_id = client.user_id_from_username(username)
    threads = client.direct_threads()
    for thread in threads:
        if user_id in [user.pk for user in thread.users]:
            return True
    return False

def check_unread_messages(account):
    client = login(account['ig_username'], account['ig_password'])
    if not client:
        return
    threads = client.direct_threads()
    last_unread_message = None
    for thread in threads:
        for message in reversed(thread.messages):
            if not message.is_sent_by_viewer:
                last_unread_message = {
                    "account": account['ig_username'],
                    "sender": next((user.username for user in thread.users if user.pk == message.user_id), "Unknown"),
                    "content": message.text
                }
                break
        if last_unread_message:
            break
    if last_unread_message:
        filename = f"last_unread_message_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        with open(filename, mode='w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(["Account", "Sender", "Content"])
            writer.writerow([last_unread_message["account"], last_unread_message["sender"], last_unread_message["content"]])
        logger.info(f"Last unread message saved to {filename}")
    else:
        logger.info("No unread messages found.")

def check_updates(accounts):
    threads = []
    for account in accounts:
        thread = threading.Thread(target=check_unread_messages, args=(account,))
        threads.append(thread)
        thread.start()
    for thread in threads:
        thread.join()

if __name__ == "__main__":
    download_image(IMAGE_URL, IMAGE_PATH)
    while True:
        command = input("Enter 'send' to start sending messages or 'updates' to check for unread messages: ")
        if command.lower() == 'send':
            users_to_message = read_users_from_csv('users.csv')
            BATCH_SIZE = 10
            threads = []
            for account in ACCOUNTS:
                thread = threading.Thread(target=send_messages_from_account, args=(account, users_to_message, BATCH_SIZE))
                threads.append(thread)
                thread.start()
            for thread in threads:
                thread.join()
        elif command.lower() == 'updates':
            check_updates(ACCOUNTS)
        else:
            logger.info("Invalid command. Please try again.")
