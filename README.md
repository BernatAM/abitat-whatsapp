cd /home/ec2-user/abitat-whatsapp
docker stop abitat-whatsapp-api
docker rm abitat-whatsapp-api
docker build -t abitat-whatsapp-api .
docker run -d \
  --name abitat-whatsapp-api \
  --env-file .env \
  -p 127.0.0.1:8000:8000 \
  abitat-whatsapp-api


# Abitat WhatsApp Demo Mock

Backend en FastAPI para un flujo conversacional de WhatsApp orientado a venta de toner y recogida de cartuchos vacios.

En produccion usa Supabase mediante `SUPABASE_URL` y `SUPABASE_KEY`. Si no estan configuradas, usa memoria como fallback solo para desarrollo local.

Puede funcionar de dos formas:

- modo demo local usando `POST /demo/message`
- modo real con `WhatsApp Cloud API` de Meta usando webhook y envio saliente por Graph API

## Base de datos Supabase

Ejecuta primero el script SQL de creacion en Supabase. La aplicacion espera estas tablas:

- `contacts`
- `contact_flow_state`
- `messages`
- `tags`
- `contact_tags`
- `scheduled_jobs`
- `processed_events`

Configura Supabase en `.env`:

```env
SUPABASE_URL=https://tckqfyydlpqokvpdqmge.supabase.co
SUPABASE_KEY=tu_service_role_key
```

Recomendacion para Supabase:

- Usa una key server-side. Idealmente `service_role` solo en el servidor.
- No expongas `SUPABASE_KEY` en frontend.
- No subas `.env` a Git.
- Si usas Row Level Security, asegúrate de que la key del backend puede leer/escribir las tablas del flujo.

## Estructura

```text
.
|-- app
|   |-- domain
|   |   |-- models.py
|   |   `-- schemas.py
|   |-- integrations
|   |   |-- email.py
|   |   |-- sage.py
|   |   `-- whatsapp.py
|   |-- repositories
|   |   `-- memory.py
|   |-- routers
|   |   |-- debug.py
|   |   |-- demo.py
|   |   |-- health.py
|   |   `-- webhook.py
|   |-- services
|   |   |-- config.py
|   |   |-- container.py
|   |   |-- conversation.py
|   |   `-- jobs.py
|   |-- utils
|   |   `-- parsing.py
|   `-- main.py
|-- Dockerfile
|-- docker-compose.yml
|-- requirements.txt
`-- README.md
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
source .venv/bin/activate
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

## Variables de entorno para WhatsApp real

Necesitas estas variables para integrar Supabase y Meta:

- `SUPABASE_URL`
- `SUPABASE_KEY`
- `WHATSAPP_VERIFY_TOKEN`
- `WHATSAPP_ACCESS_TOKEN`
- `WHATSAPP_PHONE_NUMBER_ID`
- opcional: `WHATSAPP_GRAPH_VERSION` con valor por defecto `v23.0`

Ejemplo:

```env
SUPABASE_URL=https://tckqfyydlpqokvpdqmge.supabase.co
SUPABASE_KEY=tu_service_role_key
WHATSAPP_VERIFY_TOKEN=un_token_largo_y_privado
WHATSAPP_ACCESS_TOKEN=EAAG...
WHATSAPP_PHONE_NUMBER_ID=123456789012345
WHATSAPP_GRAPH_VERSION=v23.0
```

Con Docker Compose:

```bash
docker compose --env-file .env up --build
```

## Endpoints

- `GET /health`
- `POST /demo/message`
- `GET /webhook/whatsapp`
- `POST /webhook/whatsapp`
- `GET /debug/conversations`
- `GET /debug/conversations/{phone}`
- `POST /debug/conversations/{phone}/reset`
- `GET /debug/jobs`
- `POST /debug/jobs/run`
- `POST /debug/sage/{phone}/exists`
- `POST /debug/sage/{phone}/new`

## Demo local

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

## Webhook simulado

```bash
curl -X POST http://localhost:8000/webhook/whatsapp \
  -H "Content-Type: application/json" \
  -d '{
    "message": {
      "from": "+34600000000",
      "text": "Si"
    }
  }'
```

## Configuracion con Meta Cloud API real

### 1. Configura el webhook en Meta

En Meta for Developers, configura:

- Callback URL: `https://tu-dominio.com/webhook/whatsapp`
- Verify Token: el mismo valor de `WHATSAPP_VERIFY_TOKEN`

La verificacion de Meta llega por `GET /webhook/whatsapp` con `hub.mode`, `hub.verify_token` y `hub.challenge`. Si el token coincide, la API devuelve el challenge.

### 2. Suscribe eventos

En el producto WhatsApp de Meta suscribe al menos el campo `messages`.

### 3. Configura credenciales de salida

- `WHATSAPP_ACCESS_TOKEN`: token de acceso de Meta
- `WHATSAPP_PHONE_NUMBER_ID`: identificador del numero emisor

### 4. Funcionamiento

Cuando Meta envia un mensaje de texto entrante al webhook:

- se extrae el telefono del cliente
- se procesa el flujo conversacional
- se guarda el contacto, estado, tags, mensajes y jobs en Supabase
- cada respuesta generada se envia de vuelta por Graph API

### 5. Importante sobre la ventana de 24 horas

Las respuestas de texto libre funcionan dentro de la ventana de servicio al cliente de WhatsApp. Para contactar fuera de esa ventana tendras que usar plantillas aprobadas por Meta.

## Conversacion de ejemplo

### Cliente existente con recogida

```bash
curl -X POST http://localhost:8000/demo/message -H "Content-Type: application/json" -d '{"phone":"+34600000000","text":"Hola"}'
curl -X POST http://localhost:8000/demo/message -H "Content-Type: application/json" -d '{"phone":"+34600000000","text":"Si"}'
curl -X POST http://localhost:8000/demo/message -H "Content-Type: application/json" -d '{"phone":"+34600000000","text":"HP LaserJet Pro M404dn"}'
curl -X POST http://localhost:8000/demo/message -H "Content-Type: application/json" -d '{"phone":"+34600000000","text":"Ecologico Abitat"}'
curl -X POST http://localhost:8000/demo/message -H "Content-Type: application/json" -d '{"phone":"+34600000000","text":"3"}'
curl -X POST http://localhost:8000/demo/message -H "Content-Type: application/json" -d '{"phone":"+34600000000","text":"Si"}'
curl -X POST http://localhost:8000/demo/message -H "Content-Type: application/json" -d '{"phone":"+34600000000","text":"2"}'
curl -X POST http://localhost:8000/demo/message -H "Content-Type: application/json" -d '{"phone":"+34600000000","text":"Original"}'
curl -X POST http://localhost:8000/demo/message -H "Content-Type: application/json" -d '{"phone":"+34600000000","text":"Martes por la manana"}'
```

### Cliente nuevo con presupuesto y recogida

```bash
curl -X POST http://localhost:8000/demo/message -H "Content-Type: application/json" -d '{"phone":"+34600000001","text":"Hola"}'
curl -X POST http://localhost:8000/demo/message -H "Content-Type: application/json" -d '{"phone":"+34600000001","text":"Si necesito"}'
curl -X POST http://localhost:8000/demo/message -H "Content-Type: application/json" -d '{"phone":"+34600000001","text":"Brother HL-L2375DW"}'
curl -X POST http://localhost:8000/demo/message -H "Content-Type: application/json" -d '{"phone":"+34600000001","text":"Compatible"}'
curl -X POST http://localhost:8000/demo/message -H "Content-Type: application/json" -d '{"phone":"+34600000001","text":"4"}'
curl -X POST http://localhost:8000/demo/message -H "Content-Type: application/json" -d '{"phone":"+34600000001","text":"Calle Mayor 10, Madrid compras@cliente.es"}'
curl -X POST http://localhost:8000/demo/message -H "Content-Type: application/json" -d '{"phone":"+34600000001","text":"Si"}'
curl -X POST http://localhost:8000/demo/message -H "Content-Type: application/json" -d '{"phone":"+34600000001","text":"6"}'
curl -X POST http://localhost:8000/demo/message -H "Content-Type: application/json" -d '{"phone":"+34600000001","text":"Compatible"}'
curl -X POST http://localhost:8000/demo/message -H "Content-Type: application/json" -d '{"phone":"+34600000001","text":"Jueves 16:00 a 18:00"}'
```

### No necesito ahora

```bash
curl -X POST http://localhost:8000/demo/message -H "Content-Type: application/json" -d '{"phone":"+34600000003","text":"Hola"}'
curl -X POST http://localhost:8000/demo/message -H "Content-Type: application/json" -d '{"phone":"+34600000003","text":"Mas adelante"}'
```

## Debug y testing

### Ver conversaciones

```bash
curl http://localhost:8000/debug/conversations
```

### Ver una conversacion

```bash
curl http://localhost:8000/debug/conversations/+34600000000
```

### Resetear una conversacion

```bash
curl -X POST http://localhost:8000/debug/conversations/+34600000000/reset
```

### Ver jobs

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

### Forzar resultado del mock SAGE

```bash
curl -X POST http://localhost:8000/debug/sage/+34600000999/exists
curl -X POST http://localhost:8000/debug/sage/+34600000999/new
```

## Estado en memoria

Cada conversacion guarda:

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

## Notas

- Una conversacion por telefono.
- Estado productivo guardado en Supabase si `SUPABASE_URL` y `SUPABASE_KEY` estan configuradas.
- Fallback en memoria solo para desarrollo local.
- Historial con `timestamp`, `direction`, `text`, `state_before`, `state_after`.
- Logs por mensaje recibido, transiciones, tags, resultado SAGE y jobs.
- El webhook soporta payload simulado y payload real de Meta para mensajes de texto.
- Idempotencia basica para mensajes entrantes reales usando `processed_events`.
