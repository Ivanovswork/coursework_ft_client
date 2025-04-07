import asyncio
import json
import socket
import os

# --- Конфигурация клиента ---
SERVER_HOST = '127.0.0.1'  # Или IP-адрес сервера в сети
SERVER_PORT = 12345
CHUNK_SIZE = 8192  # Должен совпадать с размером на сервере


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
        response = response.decode('utf-8')
        if response == "NO":
            print("Клиент: Сервер отказал в подключении")
            return f"Error connecting to server"
        request = f"{command} {filename}"
        await loop.sock_sendall(client_socket, request.encode('utf-8'))

        if command == "GET":
            response = await loop.sock_recv(client_socket, 1024)
            response = response.decode('utf-8')

            if response.startswith("OK"):
                file_size = int(response[3:].strip())  # Извлекаем размер файла
                print(f"Клиент: Получен размер файла от сервера: {file_size}")
                await loop.sock_sendall(client_socket, "READY".encode('utf-8'))  # Отправляем подтверждение
                success = await receive_file(loop, client_socket, filename, file_size)
                if not success:
                    print("Клиент: Ошибка при получении файла.")
            else:
                print(f"Клиент: Error: {response}")

        elif command == "PUT":
            file_size = os.path.getsize(filepath)
            response = await loop.sock_recv(client_socket, 1024)
            response = response.decode('utf-8')
            if response == "READY":
                print(f"Клиент: Размер отправляемого файла: {file_size}")
                await loop.sock_sendall(client_socket, str(file_size).encode('utf-8'))

            response = await loop.sock_recv(client_socket, 1024)
            response = response.decode('utf-8')

            if response == "READY":
                success = await send_file(loop, client_socket, filepath)
                if success:
                    response = await loop.sock_recv(client_socket, 1024)
                    print(f"Клиент: {response.decode('utf-8')}")
                else:
                    print("Клиент: Ошибка при отправке файла.")
            else:
                print(f"Клиент: Error: {response}")

        elif command == "LIST":
            response = await loop.sock_recv(client_socket, 4096)
            response = response.decode('utf-8')
            if response.startswith("OK"):
                files_info = json.loads(response[3:].strip())
                print("Клиент: Список файлов:")
                for file_data in files_info:
                    print(f"  Имя: {file_data['name']}, Размер: {file_data['size']} байт")
            else:
                print(f"Клиент: Error: {response}")
        elif command == "DELETE":
            response = await loop.sock_recv(client_socket, 1024)
            response = response.decode('utf-8')
            print(f"Клиент: {response}")

        client_socket.close()

    except socket.error as e:
        return f"Error connecting to server: {e}"
    except Exception as e:
        return f"Error: {str(e)}"


async def main():
    # --- Пример использования ---
    # 1. Получить список файлов
    await send_request("LIST")

    # 2. Получить содержимое файла
    # await send_request("GET", "f.docx")
    #
    # # 3. Записать файл на сервер
    # await send_request("PUT", "d.docx", "d.docx")  # Третьим аргументом имя файла, который будем отправлять, а не содержимое

    await send_request("DELETE", "d.docx")
    # # 4. Повторно получить список файлов для проверки
    await send_request("LIST")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())