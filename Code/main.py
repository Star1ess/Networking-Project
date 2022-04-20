import struct
import os
import zipfile
from os.path import join
import threading
import argparse
from socket import *

ip = ''
file_dict = {}
folder = 'share'
main_port = 22500
file_port = 27500
file_buffer_size = 102400

receive_socket = socket(AF_INET, SOCK_STREAM)
receive_socket.bind(('', file_port))  # 20000 to 30000
receive_socket.listen(2)


def _argparse():
    global ip
    parser = argparse.ArgumentParser(description='This is description')
    parser.add_argument('--ip', action='store', required=True, dest='ip', help='The IP address of another computer')
    ip = parser.parse_args().ip


def compress_file(folder_name):
    print('Start compressing ', folder_name)
    package = zipfile.ZipFile(join(folder_name + '.zip'), 'w', zipfile.ZIP_DEFLATED)
    file_list = os.listdir(join('share', folder_name))
    for f in file_list:
        package.write(join('share', folder_name, f), join('share', folder_name + '.dl', f))
    package.close()
    print(folder_name, ' compressed')


def decompress_file(folder_name, mtime):
    print('Start decompressing ', folder_name)
    zip_folder = folder_name + '.zip'
    package = zipfile.ZipFile(zip_folder, 'r')
    package.extractall()
    package.close()
    os.utime(join('share', folder_name + '.dl'), (mtime, mtime))
    if os.path.exists(join('share', folder_name)):
        for file in os.listdir(join('share', folder_name)):
            os.remove(join('share', folder_name, file))
        os.removedirs(join('share', folder_name))
    os.rename(join('share', folder_name + '.dl'), join('share', folder_name))
    print(folder_name, ' decompressed')


def make_header(instruction_code, name, mtime, position, port):
    header = struct.pack('!IdII', instruction_code, mtime, position, port) + name.encode()
    return header


def parse_header(file):
    instruction_code, mtime, position, port = struct.unpack('!IdII', file[:20])
    name = file[20:].decode()
    return instruction_code, name, mtime, position, port


def send_message(msg):
    send_message_socket = socket(AF_INET, SOCK_STREAM)
    while True:
        try:
            send_message_socket.connect((ip, main_port))
            send_message_socket.sendall(msg)
            break
        except(ConnectionRefusedError, TimeoutError, ConnectionResetError):
            pass
    print('Send ', parse_header(msg), ' to ', ip)


def receive_message():
    receive_message_socket = socket(AF_INET, SOCK_STREAM)
    receive_message_socket.bind(('', main_port))
    receive_message_socket.listen(10)

    while True:
        connectionSocket, address = receive_message_socket.accept()
        message_collection = b''
        message = connectionSocket.recv(1500)
        message_collection += message
        while len(message) > 0:
            message = connectionSocket.recv(1500)
            message_collection += message
        instruction_code, name, mtime, position, port = parse_header(message_collection)
        print('Received ', instruction_code, name, mtime, position, port, ' from ', address[0])
        if instruction_code == 0:  # Request send file
            send_file(join('share', name), port, 0)
        elif instruction_code == 1:   # Modify file
            header = make_header(0, name, mtime, 0, file_port)
            send_message(header)
            receive_file(join('share', name), receive_socket, mtime, 0)
        elif instruction_code == 2:   # Add file
            if not os.path.exists(join('share', name)):
                header = make_header(0, name, mtime, 0, file_port)
                send_message(header)
                receive_file(join('share', name), receive_socket, mtime, 0)
        elif instruction_code == 3:   # Request send folder
            send_folder(name, port, 0)
        elif instruction_code == 4:   # Add folder
            if not os.path.exists(join('share', name)):
                header = make_header(3, name, mtime, 0, file_port)
                send_message(header)
                receive_folder(name, receive_socket, mtime, position)
        elif instruction_code == 5:   # Request reload file
            header = make_header(7, name, mtime, position, 0)
            send_message(header)
            send_file(join('share', name), port, position)
        elif instruction_code == 6:   # Request reload folder
            header = make_header(8, name, mtime, position, 0)
            send_message(header)
            send_file(join('share', name), file_port, position)
        elif instruction_code == 7:   # Continue receive file based on received size
            receive_file(join('share', name), receive_socket, mtime, position)
        elif instruction_code == 8:   # Continue receive folder based on received size
            receive_file(name, receive_socket, mtime, position)
        elif instruction_code == 10:   # Start
            for file in file_dict:
                if os.path.isfile(join('share', file)):
                    header = make_header(2, file, file_dict[file], 0, 0)
                    send_message(header)
                else:
                    header = make_header(4, file, file_dict[file], 0, 0)
                    send_message(header)
        connectionSocket.close()


def send_folder(folder_path, port, position):
    compress_file(folder_path)
    name = folder_path + '.zip'
    send_file(name, port, position)


def send_file(file, port, position):
    send_file_socket = socket(AF_INET, SOCK_STREAM)
    f = open(file, 'rb')
    f.seek(position)
    try:
        send_file_socket.connect((ip, port))
        send_file_data = f.read(file_buffer_size)
        send_file_socket.sendall(send_file_data)
        while len(send_file_data) > 0:
            send_file_data = f.read(file_buffer_size)
            send_file_socket.sendall(send_file_data)
        f.close()
        print('Finish sending')
    except(ConnectionRefusedError, TimeoutError, ConnectionResetError):
        print('Not finish sending', file)
    send_file_socket.close()


def receive_folder(folder_name, receive_socket, mtime, position):
    receive_file(folder_name + '.zip', receive_socket, mtime, position)
    decompress_file(folder_name, mtime)


def receive_file(file_name, receive_socket, mtime, position):
    print('Start receiving ', file_name)
    while True:
        connection_socket, address = receive_socket.accept()
        if os.path.exists(file_name + '.dl'):
            f = open(file_name + '.dl', 'rb+')
        else:
            f = open(file_name + '.dl', 'wb')
        f.seek(position)

        receive_file_data = connection_socket.recv(file_buffer_size)
        f.write(receive_file_data)
        while len(receive_file_data) > 0:
            receive_file_data = connection_socket.recv(file_buffer_size)
            f.write(receive_file_data)
        f.close()
        print('Writing finished')
        connection_socket.close()
        break

    if os.path.split(file_name)[-1] in file_dict:
        file_dict[os.path.split(file_name)[-1]] = mtime
    os.utime(join(file_name + '.dl'), (mtime, mtime))
    if os.path.exists(file_name):
        os.remove(file_name)
    os.rename(file_name + '.dl', file_name)
    print(file_name, ' received')


def scan_reload(path):
    print('Start scanning ', path)
    for file in os.listdir(path):
        if file[-3:] == '.dl':
            position = os.path.getsize(join(path, file))
            # Package and send messages according to protocol
            if path is None:
                header = make_header(6, file[:-3], 0, position, file_port)
            elif '.' not in file[:-3]:   # folder
                header = make_header(6, file[:-3], 0, position, file_port)
            else:   # file
                header = make_header(5, file[:-3], 0, position, file_port)
            send_message(header)


def create_share_folder():
    try:
        os.mkdir('share')
        print('share folder created')
    except FileExistsError:
        print('"share" folder already exists')


def scan_share_folder():
    scan_folder = 'share'
    while True:
        for file in os.listdir(scan_folder):
            if file[-3:] == '.dl':
                continue
            mtime = os.path.getmtime(join('share', file))
            if file in file_dict:
                if file_dict[file] != mtime:   # Have been modified
                    file_dict[file] = mtime
                    print('New update for ', file)
                    if os.path.isfile(join('share', file)):
                        header = make_header(1, file, mtime, 0, 0)
                        send_message(header)
            else:   # Add new file
                print('Not exist, create new file')
                file_dict[file] = mtime
                if os.path.isfile(join('share', file)):   # Add file
                    header = make_header(2, file, mtime, 0, 0)
                else:   # Add folder
                    header = make_header(4, file, mtime, 0, 0)
                send_message(header)


def main():
    _argparse()
    create_share_folder()
    nt = threading.Thread(target=receive_message, args=())
    nt.start()

    scan_reload(None)
    scan_reload('share')

    create_share_folder()

    send_message(make_header(10, '', 0, 0, 0))
    scan_share_folder()


if __name__ == '__main__':
    main()
