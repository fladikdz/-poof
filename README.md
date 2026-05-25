# iOS Location Spoofer

DIY-аналог iMyFone AnyTo. См. `PROJECT.pdf` для полной спецификации.

## Статус: Итерация 1+2 (минимальный CLI, iOS 17+)

На iOS 17+ DVT работает только через `tunneld` / RemoteXPC. Поэтому Итерации 1
(легаси-DDI для iOS ≤16) и 2 (tunneld для iOS 17+) объединены в одну MVP-стадию.

## Установка (Windows / Linux / macOS)

```powershell
py -3.11 -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

## Подготовка iPhone (iOS 17+)

1. Подключить iPhone по USB и пройти «Trust This Computer».
2. Включить Developer Mode: `Settings → Privacy & Security → Developer Mode → On`,
   перезагрузка устройства, подтвердить включение после ребута.

## Подготовка Windows (минимальный путь, без iTunes)

`pymobiledevice3` на Windows общается с iPhone через службу `Apple Mobile Device
Service` (AMDS), слушающую `127.0.0.1:27015`. Полный iTunes не нужен — достаточно
только AMDS-MSI (~30 МБ, одна фоновая служба).

1. Скачать `iTunes64Setup.exe` с https://www.apple.com/itunes/ (не запускать!)
2. Открыть его в 7-Zip как контейнер (правой кнопкой → 7-Zip → Open archive)
3. Извлечь и установить только `AppleMobileDeviceSupport64.msi`
4. Остальные .msi (`iTunes64.msi`, `Bonjour64.msi`, `AppleApplicationSupport*.msi`)
   — **не ставить**

После этого `devices` и `tunneld` корректно видят USB-подключение.

На Linux / macOS отдельно ничего ставить не нужно — usbmuxd идёт в комплекте.

## Запуск tunneld

`tunneld` поднимает TUN-интерфейс — нужны права администратора.

**Windows** (PowerShell от имени Administrator):

```powershell
backend\.venv\Scripts\pymobiledevice3.exe remote tunneld
```

**Linux / macOS**:

```bash
sudo backend/.venv/bin/pymobiledevice3 remote tunneld
```

Оставить процесс запущенным. По умолчанию слушает `127.0.0.1:49151`.

## CLI

В отдельном окне (обычный пользователь, не admin):

```powershell
# Список подключённых и протуннелированных устройств
backend\.venv\Scripts\python.exe backend\cli_spoof.py devices

# Подмена координат (центр Варшавы) — держит сессию до Ctrl+C
backend\.venv\Scripts\python.exe backend\cli_spoof.py spoof --lat 52.2297 --lon 21.0122

# Явный сброс
backend\.venv\Scripts\python.exe backend\cli_spoof.py clear
```

**Важно:** симуляция живёт только пока процесс `spoof` запущен. Выход (Ctrl+C, краш,
закрытие окна) → iOS немедленно возвращает реальный GPS. Это особенность DVT, не баг.

## Что в Итерации 2 (после подтверждения)

Итерация 2 по PDF: «iOS 17+ поддержка» — уже реализована здесь.
Следующий шаг по плану — **Итерация 3 (Базовый GUI)**: Tauri + React + карта,
WebSocket к Python-бэку, режим Teleport из UI.

## Disclaimer

Проект для разработки, тестирования геолокационных функций и личного использования.
Соблюдайте применимое законодательство и условия использования сервисов, для
которых подменяете координаты.
