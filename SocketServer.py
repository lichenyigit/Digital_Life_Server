# encoding: utf-8
import argparse
import os
import socket
import time
import logging
import traceback
from logging.handlers import TimedRotatingFileHandler

import librosa
import requests
import revChatGPT
import soundfile
import threading

import GPT.tune
from utils.FlushingFileHandler import FlushingFileHandler
from ASR import ASRService
from GPT import GPTService
from TTS import TTService
from SentimentEngine import SentimentEngine

console_logger = logging.getLogger()
console_logger.setLevel(logging.INFO)
FORMAT = '%(asctime)s %(levelname)s %(message)s'
console_handler = console_logger.handlers[0]
console_handler.setFormatter(logging.Formatter(FORMAT))
console_logger.setLevel(logging.INFO)
file_handler = FlushingFileHandler("log.log", formatter=logging.Formatter(FORMAT))
file_handler.setFormatter(logging.Formatter(FORMAT))
file_handler.setLevel(logging.INFO)
console_logger.addHandler(file_handler)
console_logger.addHandler(console_handler)


def str2bool(v):
    if v.lower() in ('yes', 'true', 't', 'y', '1'):
        return True
    elif v.lower() in ('no', 'false', 'f', 'n', '0'):
        return False
    else:
        raise argparse.ArgumentTypeError('Unsupported value encountered.')

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--chatVer", type=int, nargs='?', required=True)
    parser.add_argument("--APIKey", type=str, nargs='?', required=False)
    parser.add_argument("--email", type=str, nargs='?', required=False)
    parser.add_argument("--password", type=str, nargs='?', required=False)
    parser.add_argument("--accessToken", type=str, nargs='?', required=False)
    parser.add_argument("--proxy", type=str, nargs='?', required=False)
    parser.add_argument("--paid", type=str2bool, nargs='?', required=False)
    parser.add_argument("--model", type=str, nargs='?', required=False)
    parser.add_argument("--stream", type=str2bool, nargs='?', required=True)
    parser.add_argument("--character", type=str, nargs='?', required=True)
    parser.add_argument("--ip", type=str, nargs='?', required=False)
    parser.add_argument("--brainwash", type=str2bool, nargs='?', required=False)
    return parser.parse_args()


class Server():
    def __init__(self, args):
        # SERVER STUFF
        self.addr = None
        self.conn = None
        # 打印顶部边框
        logging.info('*' * 24)
        # 打印中间内容
        logging.info('Initializing Server...')
        # 打印底部边框
        logging.info('*' * 24)
        
        self.host = socket.gethostbyname(socket.gethostname())
        self.port = 8800
        self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.s.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 10240000)
        self.s.bind((self.host, self.port))
        
        self.tmp_recv_file = 'tmp/server_received.wav'
        self.tmp_proc_file = 'tmp/server_processed.wav'
        self.timeout = 120#单位秒
        self.timer = None

        ## hard coded character map
        self.char_name = {
            'paimon': ['TTS/models/paimon6k.json', 'TTS/models/paimon6k_390k.pth', 'character_paimon', 1],
            'yunfei': ['TTS/models/yunfeimix2.json', 'TTS/models/yunfeimix2_53k.pth', 'character_yunfei', 1.1],
            'catmaid': ['TTS/models/catmix.json', 'TTS/models/catmix_107k.pth', 'character_catmaid', 1.2]
        }

        # PARAFORMER
        self.paraformer = ASRService.ASRService('./ASR/resources/config.yaml')

        # CHAT GPT
        self.chat_gpt = GPTService.GPTService(args)

        # TTS
        self.tts = TTService.TTService(*self.char_name[args.character])

        # Sentiment Engine
        self.sentiment = SentimentEngine.SentimentEngine('SentimentEngine/models/paimon_sentiment.onnx')

    #start add by lcy 2024年6月17日 09点45分
    def start_timer(self):
        self.timer = threading.Timer(self.timeout, self.disconnect_client)
        self.timer.start()
        logging.info("Start timer");

    def reset_timer(self):
        if self.timer:
            self.timer.cancel()
        self.start_timer()
        logging.info("Reset timer");
        
    def disconnect_client(self):
        if self.conn:
            logging.info("Disconnecting client due to inactivity.************")
            try:
                self.conn.shutdown(socket.SHUT_RDWR)
            except socket.error as e:
                logging.error(f"Error shutting down connection: {e}")
            finally:
                self.conn.close()
                self.conn = None
                logging.info("Client disconnected.**************")
                #self.reset_server()  # 重置服务器，为新的连接做好准备
        
    def reset_server(self):
        logging.info("Resetting server...")
        if self.s:
            self.s.close()
        self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.s.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 10240000)
        self.s.bind((self.host, self.port))
        logging.info(f"Server reset and listening on {self.host}:{self.port}")
        
    #end


    def listen(self):
        # MAIN SERVER LOOP
        while True:
            self.s.listen()
            logging.info(f"Server is listening on {self.host}:{self.port}...")
            self.conn, self.addr = self.s.accept()
            logging.info(f"Connected by {self.addr}")
            self.conn.sendall(b'%s' % self.char_name[args.character][2].encode())
            logging.info('你好，我准备好了')
            self.send_voice("你好，我准备好了")
            self.notice_stream_end()
            
            while True:
                try:
                    file = self.__receive_file()
                    # print('file received: %s' % file)
                    with open(self.tmp_recv_file, 'wb') as f:
                        f.write(file)
                        logging.info('WAV file received and saved.')
                    ask_text = self.process_voice()
                    if args.stream:
                        for sentence in self.chat_gpt.ask_stream(ask_text):
                            self.send_voice(sentence)
                        self.notice_stream_end()
                        logging.info('Stream finished.')
                    else:
                        resp_text = self.chat_gpt.ask(ask_text)
                        self.send_voice(resp_text)
                        self.notice_stream_end()
                except revChatGPT.typings.APIConnectionError as e:
                    logging.error(e.__str__())
                    logging.info('API rate limit exceeded, sending: %s' % GPT.tune.exceed_reply)
                    self.send_voice(GPT.tune.exceed_reply, 2)
                    self.notice_stream_end()
                except revChatGPT.typings.Error as e:
                    logging.error(e.__str__())
                    logging.info('Something wrong with OPENAI, sending: %s' % GPT.tune.error_reply)
                    self.send_voice(GPT.tune.error_reply, 1)
                    self.notice_stream_end()
                except requests.exceptions.RequestException as e:
                    logging.error(e.__str__())
                    logging.info('Something wrong with internet, sending: %s' % GPT.tune.error_reply)
                    self.send_voice(GPT.tune.error_reply, 1)
                    self.notice_stream_end()
                except Exception as e:
                    logging.error(e.__str__())
                    logging.error(traceback.format_exc())
                    break;
                finally:
                    self.reset_timer()  # 重置定时器
            self.reset_timer()  # 重置定时器        

    def notice_stream_end(self):
        try:
            time.sleep(0.5)
            self.conn.sendall(b'stream_finished')
        except ConnectionResetError as e:
            logging.error(f"Connection reset by peer during send: {e}")
        except Exception as e:
            logging.error(f"Unexpected error during send: {e}")

    def send_voice(self, resp_text, senti_or = None):
        self.tts.read_save(resp_text, self.tmp_proc_file, self.tts.hps.data.sampling_rate)
        with open(self.tmp_proc_file, 'rb') as f:
            senddata = f.read()
        if senti_or:
            senti = senti_or
        else:
            senti = self.sentiment.infer(resp_text)
        senddata += b'?!'
        senddata += b'%i' % senti
        if self.conn:
            self.conn.sendall(senddata)
        else:
            logging.error("Connection is not available for sending data.")
        time.sleep(0.5)
        logging.info('WAV SENT, size %i' % len(senddata))

    def __receive_file(self):
        file_data = b''
        while True:
            if self.conn:
                data = self.conn.recv(1024)
                # print(data)
                self.conn.send(b'sb')
                if data[-2:] == b'?!':
                    file_data += data[0:-2]
                    break
                if not data:
                    # logging.info('Waiting for WAV...')
                    continue
                file_data += data

        return file_data

    def fill_size_wav(self):
        with open(self.tmp_recv_file, "r+b") as f:
            # Get the size of the file
            size = os.path.getsize(self.tmp_recv_file) - 8
            # Write the size of the file to the first 4 bytes
            f.seek(4)
            f.write(size.to_bytes(4, byteorder='little'))
            f.seek(40)
            f.write((size - 28).to_bytes(4, byteorder='little'))
            f.flush()

    def process_voice(self):
        # stereo to mono
        self.fill_size_wav()
        y, sr = librosa.load(self.tmp_recv_file, sr=None, mono=False)
        y_mono = librosa.to_mono(y)
        y_mono = librosa.resample(y_mono, orig_sr=sr, target_sr=16000)
        soundfile.write(self.tmp_recv_file, y_mono, 16000)
        text = self.paraformer.infer(self.tmp_recv_file)

        return text


if __name__ == '__main__':
    try:
        args = parse_args()
        s = Server(args)
        s.listen()
    except Exception as e:
        logging.error(e.__str__())
        logging.error(traceback.format_exc())
        raise e
