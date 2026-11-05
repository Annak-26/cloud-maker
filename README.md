# Cloud Maker
`Cloud Maker` - проект для создания и управления виртуальными машинами на Linux с использованием QEMU/KVM и libvirt. `Cloud Maker` позволяет автоматизировать запуск и настройку виртуальных машин, управлять ими через HTTP API, реализованный на FastAPI.

## Реализованные фичи

| № | Фича | Реализация |
|---|------|------------|
| **1** | **HTTP API для управления ВМ** | `app/main.py`: `GET /vms`, `POST /vms`, `POST /vms/{name}/stop`, `DELETE /vms/{name}`. |
| **2** | **Cloud-init при запуске** | `app/vm_app.py`, функция `vm_create`: `user_data`, `ssh_key`, `hostname`. |
| **6** | **Восстановление состояния** | Состояние хранится в Libvirt. |
| **7** | **Возможность добавлять образы** | `app/img_app.py`: `GET /images` и `POST /images`. |
| **8** | **Мониторинг ресурсов** | `app/mon_app.py`: `GET /vms/{name}/stats`. |
| **9** | **Ограничение ресурсов (квоты)** | `app/vm_app.py`, функция `check()`. |
| **11** | **Скрипт для проверки** | `scripts/test_api.py`. |
| **12** | **Скрипт очистки** | `scripts/clean_up.py`. |

## Структура проекта

```text
cloud-maker/
├── app/
│   ├── main.py          
│   ├── vm_app.py        # Логика управления ВМ
│   ├── img_app.py       # Логика работы с образами
│   └── mon_app.py       # Логика мониторинга ресурсов
├── cloud-init/
│   ├── user-data        # Шаблон конфигурации cloud-init по умолчанию
│   └── meta-data
├── scripts/
│   ├── test_api.py      # Скрипт автоматической проверки API
│   └── clean_up.py      # Скрипт очистки
├── create-vm.sh         # Скрипт для проверки базового задания
├── images.json          # Зарегистрированные образы
├── requirements.txt     # Python-зависимости
└── README.md            # Документация проекта
```

## Установка зависимостей

1. Скачиваем репозиторий и переходим в папку проекта.

```bash
git clone https://github.com/Annak-26/cloud-maker.git
cd cloud-maker
```

2. Устанавливаем системные пакеты

```bash
sudo apt update
sudo apt install -y libvirt-daemon-system libvirt-dev qemu-kvm virtinst prometheus apt-transport-https cloud-image-utils python3-pip wget gnupg grafana
```

3. Устанавливаем Python-зависимости

```bash
pip install -r requirements.txt
```

## Инструкция по проверке базового задания

1. Запускаем скрипт, который скачивает образ ubuntu24 и создает виртуальную машину с именем `vm`, объемом памяти 2048 и 2 cpu. 

```bash
chmod +x create-vm.sh
sudo ./create-vm.sh
```

2. Проверяем, что виртуальная машина создалась:

```bash
sudo virsh list --all
```

3. При желании смотрим детальную информацию:

```bash
sudo virsh dominfo vm
```

4. После теста освобождаем ресурсы и удаляем тестовую виртуальную машину

```bash
python scripts/clean_up.py
```

## Инструкция по запуску сервера и проверке API

1. Даем пользователю права на скачивание базового образа и создание дисков ВМ

```bash
sudo chown -R $USER:$USER /var/lib/libvirt/images/
```

2. Запускаем FastAPI-сервер (при первом старте он скачает базовый образ ubuntu24)

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

3. В другом окне запускаем файл с автоматическими тестами всех реализованных фичей

```bash
python scripts/test_api.py
```

4. При желании проверяем программу вручную. Для этого открываем в браузере Swagger UI: `http://127.0.0.1:8000/docs`

5. После тестов освобождаем ресурсы и удаляем тестовую виртуальную машину

```bash
python scripts/clean_up.py
```
