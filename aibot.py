import socket
import time
import threading
import requests
import json

# Configuration
SERVER = "irc.oftc.net"
PORT = 6667
CHANNEL = "debian"
NICK = "hallvor"
PASSWORD = None
HUGGINGFACE_API_KEY = "YOUR HUGGINGFACE API KEY"
HUGGINGFACE_MODEL = "YOUR AI MODEL"
AI_PREFIX = ""
TRIGGER_WORD = "hallvor"
MAX_RESPONSE_LENGTH = 500
LOG_FILE = "chat_log.txt"

# Global variables
irc_socket = None
connected = False

def connect_to_irc():
    global irc_socket, connected
    while True:
        try:
            irc_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            irc_socket.connect((SERVER, PORT))
            print(f"Connected to {SERVER}:{PORT}")

            if PASSWORD:
                irc_socket.send(f"PASS {PASSWORD}\r\n".encode("utf-8"))

            irc_socket.send(f"NICK {NICK}\r\n".encode("utf-8"))
            irc_socket.send(f"USER {NICK} 0 * :{NICK}\r\n".encode("utf-8"))

            # Wait for server response
            while True:
                response = irc_socket.recv(4096).decode("utf-8", errors="ignore")
                print(f"Server response during connect: {response.strip()}")

                if "433" in response:  # Nickname already in use
                    print(f"Nickname {NICK} already in use. Appending _ to nickname.")
                    new_nick = NICK + "_"
                    irc_socket.send(f"NICK {new_nick}\r\n".encode("utf-8"))
                    irc_socket.send(f"USER {new_nick} 0 * :{new_nick}\r\n".encode("utf-8"))

                if "001" in response:  # Welcome message
                    print("Received welcome (001) message, joining channel...")
                    irc_socket.send(f"JOIN {CHANNEL}\r\n".encode("utf-8"))
                    break

            print(f"Joined channel {CHANNEL}")
            connected = True
            return

        except socket.error as e:
            print(f"Error connecting to IRC: {e}")
            print("Retrying in 10 seconds...")
            time.sleep(10)
        except Exception as e:
            print(f"Unexpected error: {e}")
            print("Retrying in 10 seconds...")
            time.sleep(10)

def send_message(channel, message):
    global irc_socket
    if irc_socket:
        try:
            irc_socket.send(f"PRIVMSG {channel} :{message}\r\n".encode("utf-8"))
            print(f"Sent message: {message}")
            log_message(NICK, message)
        except socket.error as e:
            print(f"Error sending message: {e}")
            connected = False
        except Exception as e:
            print(f"Unexpected error sending message: {e}")
            connected = False

def get_huggingface_response(prompt, model_name, api_key):
    api_url = f"https://api-inference.huggingface.co/models/{model_name}"
    headers = {"Authorization": f"Bearer {api_key}"}
    payload = {"inputs": prompt, "options": {"wait_for_model": True}}

    try:
        response = requests.post(api_url, headers=headers, json=payload, timeout=20)
        response.raise_for_status()
        json_response = response.json()

        if isinstance(json_response, list) and len(json_response) > 0 and "generated_text" in json_response[0]:
            return json_response[0]["generated_text"]
        elif isinstance(json_response, dict) and "error" in json_response:
            error_message = json_response["error"]
            print(f"Hugging Face API Error: {error_message}")
            return f"Hugging Face API Error: {error_message}"
        else:
            return "Error: Unexpected response format."

    except requests.exceptions.RequestException as e:
        print(f"Request error: {e}")
        return f"Error: {e}"
    except Exception as e:
        print(f"Unexpected error fetching HuggingFace response: {e}")
        return f"Error: {e}"

def log_message(sender_nick, message):
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            timestamp = time.strftime("[%Y-%m-%d %H:%M:%S]", time.localtime())
            f.write(f"{timestamp} <{sender_nick}> {message}\n")
    except Exception as e:
        print(f"Failed to log message: {e}")

def handle_irc_message(message):
    global irc_socket
    try:
        message = message.strip()
        if not message:
            return

        print(f"Received: {message}")

        if message.startswith("PING"):
            server = message.split()[1]
            irc_socket.send(f"PONG {server}\r\n".encode("utf-8"))
            print(f"Sent PONG to {server}")
            return

        if "PRIVMSG" in message and CHANNEL in message:
            try:
                sender_nick = message.split("!")[0].split(":")[-1]
                channel_msg = message.split(CHANNEL + " :")[-1]

                log_message(sender_nick, channel_msg)

                if channel_msg.lower().startswith(TRIGGER_WORD.lower()):
                    prompt = channel_msg[len(TRIGGER_WORD):].strip(":, ").strip()

                    if not prompt:
                        send_message(CHANNEL, f"{sender_nick}, please provide a prompt after {TRIGGER_WORD}.")
                        return

                    print(f"Generating AI response for prompt: {prompt}")
                    response = get_huggingface_response(prompt, HUGGINGFACE_MODEL, HUGGINGFACE_API_KEY)
                    response = response.replace(prompt, "", 1).strip()
                    if not response:
                        response = "Sorry, I prefer not to answer that."

                    if len(response) > MAX_RESPONSE_LENGTH:
                        response = response[:MAX_RESPONSE_LENGTH] + "..."

                    send_message(CHANNEL, f"{AI_PREFIX}{response}")

            except IndexError:
                print(f"Ignoring message with invalid format: {message}")

    except Exception as e:
        print(f"Error handling message: {e}")

def receive_messages():
    global irc_socket, connected
    while True:
        try:
            if not irc_socket:
                print("Socket missing, reconnecting...")
                connect_to_irc()
                time.sleep(5)
                continue

            data = irc_socket.recv(4096).decode("utf-8", errors="ignore")
            if not data:
                print("Disconnected from server.")
                connected = False
                irc_socket.close()
                irc_socket = None
                connect_to_irc()
                continue

            for line in data.splitlines():
                handle_irc_message(line)

        except socket.error as e:
            print(f"Socket error: {e}")
            connected = False
            irc_socket = None
            connect_to_irc()
        except Exception as e:
            print(f"Unexpected error: {e}")
            connected = False
            irc_socket = None
            connect_to_irc()

def main():
    connect_to_irc()

    if not connected:
        print("Could not connect to server, exiting...")
        return

    receive_thread = threading.Thread(target=receive_messages)
    receive_thread.daemon = True
    receive_thread.start()

    try:
        while True:
            time.sleep(60)
            if not connected:
                print("Not connected, reconnecting...")
                connect_to_irc()
    except KeyboardInterrupt:
        print("Interrupted, exiting...")
    finally:
        if irc_socket:
            irc_socket.close()

if __name__ == "__main__":
    main()

