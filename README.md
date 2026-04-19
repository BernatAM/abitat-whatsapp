# Abitat WhatsApp Demo Mock

Demo backend en `FastAPI` para simular un flujo conversacional de WhatsApp orientado a venta de tóner y recogida de cartuchos vacíos.

No usa base de datos, Redis ni colas. Todo el estado se guarda en memoria por teléfono.

## Estructura

```text
.
├── app
│   ├── domain
│   │   ├── models.py
│   │   └── schemas.py
│   ├── integrations
│   │   ├── email.py
│   │   └── sage.py
│   ├── repositories
│   │   └── memory.py
│   ├── routers
│   │   ├── debug.py
│   │   ├── demo.py
│   │   ├── health.py
│   │   └── webhook.py
│   ├── services
│   │   ├── container.py
│   │   ├── conversation.py
│   │   └── jobs.py
│   ├── utils
│   │   └── parsing.py
│   └── main.py
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── README.md
```

## Arranque

### Docker Compose

```bash
docker compose up --build
```

La API queda disponible en `http://localhost:8000`.

### Local sin Docker

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

En Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Endpoints

- `GET /health`
- `POST /demo/message`
- `POST /webhook/whatsapp`
- `GET /debug/conversations`
- `GET /debug/conversations/{phone}`
- `POST /debug/conversations/{phone}/reset`
- `GET /debug/jobs`
- `POST /debug/jobs/run`
- `POST /debug/sage/{phone}/exists`
- `POST /debug/sage/{phone}/new`

## Formato demo simplificado

### Enviar mensaje

```bash
curl -X POST http://localhost:8000/demo/message \
  -H "Content-Type: application/json" \
  -d '{
    "phone": "+34600000000",
    "text": "Hola"
  }'
```

### Respuesta esperada

```json
{
  "phone": "+34600000000",
  "state": "awaiting_need_now",
  "replies": [
    "Hola 👋 ¿Necesitas tóner ahora mismo?"
  ]
}
```

## Formato webhook WhatsApp simulado

```bash
curl -X POST http://localhost:8000/webhook/whatsapp \
  -H "Content-Type: application/json" \
  -d '{
    "message": {
      "from": "+34600000000",
      "text": "Sí"
    }
  }'
```

## Conversación de ejemplo

### Camino cliente existente con recogida

Teléfono par, por ejemplo `+34600000000`, devuelve cliente existente en el mock de SAGE.

```bash
curl -X POST http://localhost:8000/demo/message -H "Content-Type: application/json" -d '{"phone":"+34600000000","text":"Hola"}'
curl -X POST http://localhost:8000/demo/message -H "Content-Type: application/json" -d '{"phone":"+34600000000","text":"Sí"}'
curl -X POST http://localhost:8000/demo/message -H "Content-Type: application/json" -d '{"phone":"+34600000000","text":"HP LaserJet Pro M404dn"}'
curl -X POST http://localhost:8000/demo/message -H "Content-Type: application/json" -d '{"phone":"+34600000000","text":"Ecológico Ábitat"}'
curl -X POST http://localhost:8000/demo/message -H "Content-Type: application/json" -d '{"phone":"+34600000000","text":"3"}'
curl -X POST http://localhost:8000/demo/message -H "Content-Type: application/json" -d '{"phone":"+34600000000","text":"Sí"}'
curl -X POST http://localhost:8000/demo/message -H "Content-Type: application/json" -d '{"phone":"+34600000000","text":"2"}'
curl -X POST http://localhost:8000/demo/message -H "Content-Type: application/json" -d '{"phone":"+34600000000","text":"Original"}'
curl -X POST http://localhost:8000/demo/message -H "Content-Type: application/json" -d '{"phone":"+34600000000","text":"Martes por la mañana"}'
```

### Camino cliente nuevo con presupuesto y recogida

Teléfono impar, por ejemplo `+34600000001`, devuelve cliente nuevo en el mock de SAGE.

```bash
curl -X POST http://localhost:8000/demo/message -H "Content-Type: application/json" -d '{"phone":"+34600000001","text":"Hola"}'
curl -X POST http://localhost:8000/demo/message -H "Content-Type: application/json" -d '{"phone":"+34600000001","text":"Sí necesito"}'
curl -X POST http://localhost:8000/demo/message -H "Content-Type: application/json" -d '{"phone":"+34600000001","text":"Brother HL-L2375DW"}'
curl -X POST http://localhost:8000/demo/message -H "Content-Type: application/json" -d '{"phone":"+34600000001","text":"Compatible"}'
curl -X POST http://localhost:8000/demo/message -H "Content-Type: application/json" -d '{"phone":"+34600000001","text":"4"}'
curl -X POST http://localhost:8000/demo/message -H "Content-Type: application/json" -d '{"phone":"+34600000001","text":"Calle Mayor 10, Madrid compras@cliente.es"}'
curl -X POST http://localhost:8000/demo/message -H "Content-Type: application/json" -d '{"phone":"+34600000001","text":"Sí"}'
curl -X POST http://localhost:8000/demo/message -H "Content-Type: application/json" -d '{"phone":"+34600000001","text":"6"}'
curl -X POST http://localhost:8000/demo/message -H "Content-Type: application/json" -d '{"phone":"+34600000001","text":"Compatible"}'
curl -X POST http://localhost:8000/demo/message -H "Content-Type: application/json" -d '{"phone":"+34600000001","text":"Jueves 16:00 a 18:00"}'
```

### Camino no necesito ahora

```bash
curl -X POST http://localhost:8000/demo/message -H "Content-Type: application/json" -d '{"phone":"+34600000003","text":"Hola"}'
curl -X POST http://localhost:8000/demo/message -H "Content-Type: application/json" -d '{"phone":"+34600000003","text":"Más adelante"}'
```

Esto crea un job de reminder a 45 días.

## Debug y testing

### Ver todas las conversaciones

```bash
curl http://localhost:8000/debug/conversations
```

### Ver una conversación

```bash
curl http://localhost:8000/debug/conversations/+34600000000
```

### Resetear una conversación

```bash
curl -X POST http://localhost:8000/debug/conversations/+34600000000/reset
```

### Ver jobs programados

```bash
curl http://localhost:8000/debug/jobs
```

### Ejecutar jobs vencidos

```bash
curl -X POST http://localhost:8000/debug/jobs/run \
  -H "Content-Type: application/json" \
  -d '{"mode":"due"}'
```

### Ejecutar todos los jobs

```bash
curl -X POST http://localhost:8000/debug/jobs/run \
  -H "Content-Type: application/json" \
  -d '{"mode":"all"}'
```

Al ejecutar un reminder, el envío de email se simula en logs.

### Forzar resultado del mock SAGE

#### Forzar cliente existente

```bash
curl -X POST http://localhost:8000/debug/sage/+34600000999/exists
```

#### Forzar cliente nuevo

```bash
curl -X POST http://localhost:8000/debug/sage/+34600000999/new
```

## Estado en memoria

Cada conversación guarda:

- `phone`
- `current_state`
- `tags`
- `printer_raw`
- `toner_type`
- `toner_units`
- `sage_customer_exists`
- `delivery_address`
- `budget_email`
- `empty_pickup_requested`
- `empty_units`
- `empty_type`
- `pickup_slot_text`
- `history`
- `created_at`
- `updated_at`

## Notas de implementación

- Una conversación por teléfono.
- Estado guardado en diccionarios y listas en memoria.
- Historial con `timestamp`, `direction`, `text`, `state_before`, `state_after`.
- Logs por mensaje recibido, transiciones, tags, resultado SAGE y jobs.
- No hay persistencia: al reiniciar el contenedor se pierde el estado, que es justo el comportamiento esperado para la demo.
