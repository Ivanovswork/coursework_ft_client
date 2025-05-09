import asyncio
import json
import socket
import os

# --- Конфигурация клиента ---
SERVER_HOST = '127.0.0.1'  # IP-адрес сервера в сети
SERVER_PORT = 12345
CHUNK_SIZE = 65535  # Должен совпадать с размером на сервере

GET = b'\x01'
PUT = b'\x02'
DELETE = b'\x03'
LIST = b'\x04'
RESPONSE = b'\x05'

FileNotFound = b'\x01'
ConnectionBreak = b'\x02'
СhecksumError = b'\x03'

FLAG_ERROR = b'\x80'
FLAG_SIZE = b'\x40'
FLAG_STATUS = b'\x20'

STATUS_OK = b"\x80"
STATUS_NOTOK = b"\x00"


# --- Функции клиента ---
async def send_file(loop, client_socket, filepath):
    """Отправляет файл по частям."""
    try:
        with open(filepath, 'rb') as file:
            bytes_sent = 0
            while True:
                chunk = file.read(CHUNK_SIZE)  # Читаем кусок файла
                if not chunk:
                    break  # Конец файла
                await loop.sock_sendall(client_socket, chunk)
                bytes_sent += len(chunk)
                print(f"Клиент: Отправлен кусок ({len(chunk)} байт), всего отправлено {bytes_sent} байт")
        print(f"Клиент: Файл '{os.path.basename(filepath)}' успешно отправлен.")
        return True
    except FileNotFoundError:
        print("Клиент: Файл не найден")
        return False
    except Exception as e:
        print(f"Клиент: Ошибка при отправке файла: {e}")
        return False


async def receive_file(loop, client_socket, filepath, file_size):
    """Получает файл по частям."""
    try:
        with open(filepath, 'wb') as file:
            bytes_received = 0
            while bytes_received < file_size:
                chunk = await loop.sock_recv(client_socket, CHUNK_SIZE)
                if not chunk:
                    print("Клиент: Соединение с сервером прервано во время передачи.")
                    return False  # Соединение прервано
                file.write(chunk)
                bytes_received += len(chunk)
                print(f"Клиент: Получен кусок ({len(chunk)} байт), всего получено {bytes_received} байт из {file_size}")
        print(f"Клиент: Файл '{os.path.basename(filepath)}' успешно получен.")
        return True  # Файл успешно получен
    except Exception as e:
        print(f"Клиент: Ошибка при получении файла: {e}")
        return False


async def send_request(command, filename="", filepath=""):
    """Отправляет запрос на сервер и получает ответ."""
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client_socket.setblocking(False)

    loop = asyncio.get_running_loop()

    try:
        await loop.sock_connect(client_socket, (SERVER_HOST, SERVER_PORT))
        response = await loop.sock_recv(client_socket, 1024)
        if response[2:3] == STATUS_NOTOK:
            print("Клиент: Сервер отказал в подключении")
            return f"Error connecting to server"
        # request = f"{command} {filename}"
        # await loop.sock_sendall(client_socket, request.encode('utf-8'))

        if command == "GET":
            request = GET + len(filename).to_bytes(2, "big") + filename.encode("utf-8")
            print(request)
            await loop.sock_sendall(client_socket, request)

            response = await loop.sock_recv(client_socket, 1024)
            print(response[1:2] == FLAG_SIZE)
            if response[:1] == RESPONSE and response[1:2] == FLAG_SIZE:
                file_size = int.from_bytes(response[2:], 'big') # Извлекаем размер файла
                print(f"Клиент: Получен размер файла от сервера: {file_size}")
                await loop.sock_sendall(client_socket, RESPONSE + FLAG_STATUS + STATUS_OK)  # Отправляем подтверждение
                success = await receive_file(loop, client_socket, filename, file_size)
                if not success:
                    print("Клиент: Ошибка при получении файла.")
                    await loop.sock_sendall(client_socket, RESPONSE + FLAG_STATUS + STATUS_NOTOK)
                else:
                    await loop.sock_sendall(client_socket, RESPONSE + FLAG_STATUS + STATUS_OK)
            else:
                if response[:1] == RESPONSE and response[1:2] == FLAG_ERROR and response[2:] == FileNotFound:
                    print(f"Клиент: Ошибка: файл не найдет")
                else:
                    print(f"Клиент: Непредвиденная ошибка")

        elif command == "PUT":
            request = PUT + len(filename).to_bytes(2, "big") + filename.encode("utf-8")
            print(request)
            await loop.sock_sendall(client_socket, request)
            try:
                file_size = os.path.getsize(filepath)

                print(f"Клиент: Размер отправляемого файла: {file_size}")
                await loop.sock_sendall(client_socket, RESPONSE + FLAG_SIZE + file_size.to_bytes(4, "big"))

                response = await loop.sock_recv(client_socket, 1024)

                if response[:1] == RESPONSE and response[1:2] == FLAG_STATUS and response[2:] == STATUS_OK:
                    await send_file(loop, client_socket, filepath)
                    print(f"Сервер: Отправлен файл '{filename}', размер: {file_size} байт.")
                    response = await loop.sock_recv(client_socket, 1024)
                    if response[:1] == RESPONSE and response[1:2] == FLAG_STATUS and response[2:] == STATUS_OK:
                        print("Клиент: файл принят")
                    else:
                        print("Клиент: Ошибка принятия файла на сервере")
                else:
                    print(f"Клиент: Error: {response}")

            except FileNotFoundError:
                await loop.sock_sendall(client_socket, RESPONSE + FLAG_ERROR + FileNotFound)
            except Exception as e:
                await loop.sock_sendall(client_socket, RESPONSE + FLAG_ERROR + ConnectionBreak)

        elif command == "LIST":
            request = LIST
            # print(request)
            await loop.sock_sendall(client_socket, request)
            response = await loop.sock_recv(client_socket, 8192)
            if not(response[:1] == RESPONSE and response[1:2] == FLAG_ERROR and response[2:] == ConnectionBreak):
                offset = 0
                print("Клиент: Список файлов:")
                while response[offset:offset + 1]:
                    filename_size = int.from_bytes(response[offset:offset + 2], byteorder='big')
                    # print(filename_size)
                    # print(response[offset:offset + 2])
                    filename = response[offset + 2: offset + 2 + filename_size].decode('utf-8')
                    # print(response[offset + 2: offset + 2 + filename_size])
                    filesize = int.from_bytes(response[offset + 2 + filename_size:offset + 6 + filename_size], byteorder='big')
                    # print(response[offset + 2 + filename_size:offset + 6 + filename_size])
                    offset += offset + 6 + filename_size
                    print(f"  Имя: {filename}, Размер: {filesize} байт")
            else:
                print("Клиент: Ошибка при передаче списка файлов")
        elif command == "DELETE":
            request = DELETE + len(filename).to_bytes(2, "big") + filename.encode("utf-8")
            # print(request)
            await loop.sock_sendall(client_socket, request)
            response = await loop.sock_recv(client_socket, 1024)
            response = response.decode('utf-8')
            print(f"Клиент: {response}")
        else:
            print("Клиент: Команда введена неправильно или ее не существует")

        client_socket.close()

    except socket.error as e:
        return f"Error connecting to server: {e}"
    except Exception as e:
        return f"Error: {str(e)}"


async def main():
    # --- Пример использования ---
    # 1. Получить список файлов
    # await send_request("LIST")

    # 2. Получить содержимое файла
    # await send_request("GET", "af.zip")
    #
    # # 3. Записать файл на сервер
    # await send_request("PUT", "d.txt", "d.txt")  # Третьим аргументом имя файла, который будем отправлять, а не содержимое

    # await send_request("PUT", "test.txt", "test.txt")
    # await send_request("DELETE", "d.txt")
    # # 4. Повторно получить список файлов для проверки
    await send_request("LIST")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())