# ============================================================
# BYBIT P2P BUY + SELL CHAT BOT - FAST VERSION
# ============================================================
# TIDAK ADA AUTO-RELEASE.
# Semua release USDT tetap MANUAL.
# ============================================================

import os
import json
import time
import hmac
import hashlib
import requests

from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv


# ============================================================
# CONFIG
# ============================================================

load_dotenv()

API_KEY = os.getenv("BYBIT_API_KEY")
API_SECRET = os.getenv("BYBIT_API_SECRET")

BASE_URL = "https://api.bybit.com"

# Polling utama
CHECK_INTERVAL = 2

# Maksimal request API berjalan bersamaan
MAX_WORKERS = 10

AUTO_SEND = os.getenv("AUTO_SEND", "true").lower() == "true"

STATE_FILE = "bot_state.json"

SELL_VERIFY_STATUS = 8
NEW_ORDER_STATUS = 10
PAID_STATUS = 20
RELEASED_STATUS = 50


# ============================================================
# MESSAGES
# ============================================================

MESSAGE_1 = os.getenv(
    "MESSAGE_1",
    "Halo kak 👋 Untuk melanjutkan transaksi ini, mohon segera melakukan verifikasi keamanan terlebih dahulu."
)

SELL_MESSAGE_10 = os.getenv(
    "SELL_MESSAGE_10",
    "Verifikasi telah selesai. Silakan melakukan pembayaran sesuai nominal yang tertera pada pesanan."
)

MESSAGE_2 = os.getenv(
    "MESSAGE_2",
    "Pembayaran sedang dalam proses pengecekan. Mohon menunggu sebentar, USDT akan segera di-release setelah pembayaran terkonfirmasi. 🙏"
)

MESSAGE_3 = os.getenv(
    "MESSAGE_3",
    "✅ Pembelian telah berhasil dan USDT sudah di-release. Terima kasih telah melakukan transaksi bersama kami 🙏 Jika pelayanan kami memuaskan, mohon bantu berikan Feedback Positif. Dukungan Anda sangat berarti bagi kami! Semoga kita bisa bertransaksi kembali. 🙌"
)

BUY_MESSAGE_2 = os.getenv(
    "BUY_MESSAGE_2",
    "🇮🇩 Pembayaran telah berhasil dilakukan. Mohon segera melakukan release order. Terima kasih 🙏\n\n"
    "🇬🇧 Payment has been completed successfully. Kindly release the order. Thank you!"
)

BUY_MESSAGE_3 = os.getenv(
    "BUY_MESSAGE_3",
    "Terima kasih sudah order di CENTURY PRIME! 🙏\n\n"
    "Senang bisa melayani Anda. Jika berkenan, boleh bantu kasih feedback untuk transaksi hari ini ya. ⭐\n\n"
    "Sampai ketemu di order berikutnya! 🚀"
)


# ============================================================
# STATE
# ============================================================

def load_state():
    if not os.path.exists(STATE_FILE):
        return {}

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(state):
    tmp = STATE_FILE + ".tmp"

    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(
            state,
            f,
            indent=2,
            ensure_ascii=False
        )

    os.replace(tmp, STATE_FILE)


state = load_state()


# ============================================================
# BYBIT API
# ============================================================

def bybit_post(endpoint, payload):
    body = json.dumps(
        payload,
        separators=(",", ":"),
        ensure_ascii=False
    )

    timestamp = str(int(time.time() * 1000))
    recv_window = "5000"

    sign_payload = (
        timestamp
        + API_KEY
        + recv_window
        + body
    )

    signature = hmac.new(
        API_SECRET.encode("utf-8"),
        sign_payload.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()

    headers = {
        "X-BAPI-API-KEY": API_KEY,
        "X-BAPI-TIMESTAMP": timestamp,
        "X-BAPI-RECV-WINDOW": recv_window,
        "X-BAPI-SIGN": signature,
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(
            BASE_URL + endpoint,
            headers=headers,
            data=body,
            timeout=8
        )

        data = response.json()

    except Exception as e:
        print("REQUEST ERROR:", e)
        return None

    if response.status_code != 200:
        print(
            "HTTP ERROR:",
            response.status_code
        )
        return None

    if data.get("ret_code") != 0:
        print(
            "BYBIT API ERROR:",
            data
        )
        return None

    return data


# ============================================================
# CHAT SESSION
# ============================================================

def get_sessions():
    data = bybit_post(
        "/v5/p2p/chat/session/list_v1",
        {
            "lastId": 0,
            "size": 10,
            "readStatus": 2
        }
    )

    if not data:
        return []

    sessions = data.get(
        "result",
        {}
    ).get(
        "chatSession",
        []
    )

    return sessions if isinstance(sessions, list) else []


def get_messages(session_id):
    data = bybit_post(
        "/v5/p2p/chat/message/listpage_v1",
        {
            "lastId": 0,
            "limit": 30,
            "sessionId": str(session_id)
        }
    )

    if not data:
        return []

    messages = data.get(
        "result",
        {}
    ).get(
        "messages",
        []
    )

    return messages if isinstance(messages, list) else []


# ============================================================
# PARALLEL CHAT REQUEST
# ============================================================

def get_all_session_messages(sessions):
    result = []

    if not sessions:
        return result

    with ThreadPoolExecutor(
        max_workers=MAX_WORKERS
    ) as executor:

        futures = {}

        for session in sessions:
            sid = session.get("sessionId")

            if sid:
                futures[
                    executor.submit(
                        get_messages,
                        sid
                    )
                ] = session

        for future in as_completed(futures):
            session = futures[future]

            try:
                messages = future.result()

                result.append(
                    (
                        session,
                        messages
                    )
                )

            except Exception as e:
                print(
                    "SESSION ERROR:",
                    e
                )

    return result


# ============================================================
# EXTRACT ORDER ID
# ============================================================

def extract_order_ids(messages):
    result = set()

    for msg in messages:

        try:

            raw = msg.get(
                "message",
                ""
            )

            if not raw:
                continue

            content = (
                json.loads(raw)
                if isinstance(raw, str)
                else raw
            )

            if not isinstance(content, dict):
                continue

            if str(
                content.get("msgType", "")
            ) != "603":
                continue

            order_id = content.get(
                "orderId"
            )

            if not order_id:

                inner = content.get(
                    "content"
                )

                if isinstance(inner, str):
                    try:
                        inner = json.loads(inner)
                    except Exception:
                        inner = None

                if isinstance(inner, dict):
                    order_id = inner.get(
                        "orderId"
                    )

            if order_id:
                result.add(
                    str(order_id)
                )

        except Exception:
            continue

    return result


# ============================================================
# ORDER INFO
# ============================================================

def get_order_info(order_id):
    data = bybit_post(
        "/v5/p2p/order/info",
        {
            "orderId": str(order_id)
        }
    )

    if not data:
        return None

    result = data.get(
        "result",
        {}
    )

    return (
        result
        if isinstance(result, dict)
        else None
    )


def get_all_order_info(order_ids):
    result = {}

    if not order_ids:
        return result

    with ThreadPoolExecutor(
        max_workers=MAX_WORKERS
    ) as executor:

        futures = {
            executor.submit(
                get_order_info,
                oid
            ): oid
            for oid in order_ids
        }

        for future in as_completed(futures):

            oid = futures[future]

            try:

                order = future.result()

                if order:
                    result[
                        str(oid)
                    ] = order

            except Exception as e:
                print(
                    "ORDER ERROR:",
                    oid,
                    e
                )

    return result


# ============================================================
# DIRECTION
# ============================================================

def get_order_direction(order):

    side = order.get("side")

    if side is None:
        return None

    value = str(
        side
    ).strip().lower()

    if value in (
        "0",
        "buy",
        "buyorder"
    ):
        return "BUY"

    if value in (
        "1",
        "sell",
        "sellorder"
    ):
        return "SELL"

    return None


# ============================================================
# SEND MESSAGE
# ============================================================

def send_message(
    session_id,
    order_id,
    message
):

    payload = {
        "message": message,
        "contentType": "str",
        "sessionId": str(session_id),
        "orderId": str(order_id)
    }

    return (
        bybit_post(
            "/v5/p2p/chat/message/send_v1",
            payload
        )
        is not None
    )


# ============================================================
# RECURSIVE SEARCH
# ============================================================

def walk(value):

    if isinstance(value, dict):

        yield value

        for v in value.values():
            yield from walk(v)

    elif isinstance(value, list):

        for v in value:
            yield from walk(v)


def find_value(data, aliases):

    aliases = {
        str(x).lower()
        for x in aliases
    }

    for item in walk(data):

        for key, value in item.items():

            if (
                str(key).lower()
                in aliases
                and value not in (
                    None,
                    ""
                )
            ):
                return value

    return None


# ============================================================
# FORMAT
# ============================================================

def fmt_idr(value):

    if value is None:
        return "-"

    try:

        n = float(
            str(value).replace(
                ",",
                ""
            )
        )

        if n.is_integer():

            return (
                f"{int(n):,}"
                .replace(",", ".")
            )

        return (
            f"{n:,.2f}"
            .replace(",", "X")
            .replace(".", ",")
            .replace("X", ".")
        )

    except Exception:
        return str(value)


def fmt_usdt(value):

    if value is None:
        return "-"

    try:

        n = float(
            str(value).replace(
                ",",
                ""
            )
        )

        return (
            f"{n:.4f}"
            .rstrip("0")
            .rstrip(".")
            .replace(".", ",")
        )

    except Exception:
        return str(value)


def fmt_time(value):

    if value is None:
        return "-"

    try:

        n = int(
            float(
                str(value)
            )
        )

        dt = datetime.fromtimestamp(
            n / 1000
            if n > 10_000_000_000
            else n
        )

        return dt.strftime(
            "%d %B %Y %H:%M:%S"
        )

    except Exception:
        return str(value)


# ============================================================
# USERNAME
# ============================================================

def get_username(
    session,
    messages,
    order,
    direction
):

    candidates = []

    if isinstance(session, dict):

        candidates += [
            session.get(
                "sessionName"
            ),
            session.get(
                "sendUserNickName"
            ),
            session.get(
                "userNickName"
            ),
            session.get(
                "nickname"
            ),
            session.get(
                "nickName"
            )
        ]

    for msg in (
        messages
        if isinstance(messages, list)
        else []
    ):

        if isinstance(msg, dict):

            candidates += [
                msg.get(
                    "sendUserNickName"
                ),
                msg.get(
                    "senderNickName"
                ),
                msg.get(
                    "nickname"
                ),
                msg.get(
                    "nickName"
                )
            ]

    if direction == "SELL":

        candidates.append(
            find_value(
                order,
                [
                    "buyerNickName",
                    "buyerNickname",
                    "buyerUserName",
                    "buyerUsername",
                    "counterpartyNickName",
                    "counterpartyNickname"
                ]
            )
        )

    elif direction == "BUY":

        candidates.append(
            find_value(
                order,
                [
                    "sellerNickName",
                    "sellerNickname",
                    "sellerUserName",
                    "sellerUsername",
                    "counterpartyNickName",
                    "counterpartyNickname"
                ]
            )
        )

    for value in candidates:

        if value not in (
            None,
            ""
        ):
            return str(value)

    return "-"


# ============================================================
# REAL NAME
# SELL = BUYER
# BUY  = SELLER
# ============================================================

def get_counterparty_real_name(
    order,
    session,
    messages,
    direction
):

    combined = {
        "order": order,
        "session": session,
        "messages": messages
    }

    if direction == "SELL":

        value = find_value(
            combined,
            [
                "buyerRealName",
                "buyerFullName",
                "buyerLegalName",
                "buyerName",
                "buyerRealname",
                "buyerFullname",
                "counterpartyBuyerRealName",
                "counterpartyBuyerName",
                "recipientRealName",
                "recipientFullName",
                "counterpartyRealName",
                "counterpartyFullName"
            ]
        )

        if value not in (
            None,
            ""
        ):
            return str(value)

    if direction == "BUY":

        value = find_value(
            combined,
            [
                "sellerRealName",
                "sellerFullName",
                "sellerLegalName",
                "sellerName",
                "sellerRealname",
                "sellerFullname",
                "counterpartySellerRealName",
                "counterpartySellerName",
                "counterpartyRealName",
                "counterpartyFullName"
            ]
        )

        if value not in (
            None,
            ""
        ):
            return str(value)

    return "-"


# ============================================================
# ORDER TIME
# ============================================================

def get_order_time(
    order,
    session,
    messages
):

    value = find_value(
        order,
        [
            "createTime",
            "createdTime",
            "orderTime",
            "createTimestamp",
            "createdAt",
            "orderCreatedTime",
            "ctime",
            "createdTimestamp"
        ]
    )

    if value not in (
        None,
        ""
    ):
        return fmt_time(value)

    value = find_value(
        session,
        [
            "createTime",
            "createdTime",
            "orderTime",
            "createTimestamp",
            "createdAt",
            "orderCreatedTime",
            "timestamp",
            "time"
        ]
    )

    if value not in (
        None,
        ""
    ):
        return fmt_time(value)

    if isinstance(
        messages,
        list
    ):

        for msg in messages:

            if not isinstance(
                msg,
                dict
            ):
                continue

            value = find_value(
                msg,
                [
                    "createTime",
                    "createdTime",
                    "timestamp",
                    "time",
                    "createdAt",
                    "sendTime"
                ]
            )

            if value not in (
                None,
                ""
            ):
                return fmt_time(value)

    return "-"


# ============================================================
# DYNAMIC DETAILS
# ============================================================

def get_dynamic_details(
    order_id,
    session_id,
    session,
    order,
    direction,
    messages=None
):

    if messages is None:
        messages = get_messages(
            session_id
        )

    combined = {
        "order": order,
        "session": session,
        "messages": messages
    }

    username = get_username(
        session,
        messages,
        order,
        direction
    )

    real_name = get_counterparty_real_name(
        order,
        session,
        messages,
        direction
    )

    payment = find_value(
        combined,
        [
            "paymentMethodName",
            "paymentName",
            "bankName",
            "paymentChannel",
            "paymentMethod"
        ]
    )

    if (
        payment is None
        or str(payment).strip().isdigit()
    ):
        payment = "-"

    amount = find_value(
        combined,
        [
            "amount",
            "fiatAmount",
            "orderAmount",
            "totalAmount",
            "fiatAmountInCurrency",
            "priceAmount"
        ]
    )

    price = find_value(
        combined,
        [
            "price",
            "unitPrice",
            "orderPrice",
            "fiatPrice"
        ]
    )

    total = find_value(
        combined,
        [
            "quantity",
            "qty",
            "amountCrypto",
            "cryptoAmount",
            "totalQuantity",
            "coinAmount",
            "volume"
        ]
    )

    fee = find_value(
        combined,
        [
            "fee",
            "transactionFee",
            "serviceFee",
            "tradeFee",
            "feeAmount"
        ]
    )

    order_time = get_order_time(
        order,
        session,
        messages
    )

    return {
        "username": username,
        "real_name": str(real_name),
        "amount": fmt_idr(amount),
        "price": fmt_idr(price),
        "total": fmt_usdt(total),
        "fee": fmt_usdt(
            0 if fee is None else fee
        ),
        "payment": str(payment),
        "order_id": str(order_id),
        "time": order_time
    }


# ============================================================
# BUY MESSAGE 1
# ============================================================

def build_buy_message_1(
    order_id,
    session_id,
    session,
    order,
    messages=None
):

    d = get_dynamic_details(
        order_id,
        session_id,
        session,
        order,
        "BUY",
        messages
    )

    return (
        "💰 PEMBAYARAN SEDANG DIPROSES\n\n"

        f"👤 Username: {d['username']}\n"
        f"🪪 Nama: {d['real_name']}\n"
        f"💵 Jumlah: Rp{d['amount']}\n"
        f"📈 Harga: Rp{d['price']}\n"
        f"🪙 Jumlah Total: {d['total']} USDT\n"
        f"💳 Biaya Transaksi: {d['fee']} USDT\n"
        f"🏦 Pembayaran: {d['payment']}\n\n"

        f"📋 No. Pesanan: {d['order_id']}\n\n"

        f"📅 Waktu Order: {d['time']}\n\n"

        "Mohon menunggu sebentar, kami sedang melakukan pembayaran sesuai antrian. 🙏"
    )


# ============================================================
# SELL MESSAGE 2
# ============================================================

def build_sell_message_2(
    order_id,
    session_id,
    session,
    order,
    messages=None
):

    d = get_dynamic_details(
        order_id,
        session_id,
        session,
        order,
        "SELL",
        messages
    )

    return (
        "💰 PEMBAYARAN SEDANG DIPROSES\n\n"

        f"👤 Username: {d['username']}\n"
        f"🪪 Nama: {d['real_name']}\n"
        f"💵 Jumlah: Rp{d['amount']}\n"
        f"📈 Harga: Rp{d['price']}\n"
        f"🪙 Jumlah Total: {d['total']} USDT\n"
        f"💳 Biaya Transaksi: {d['fee']} USDT\n"
        f"🏦 Pembayaran: {d['payment']}\n\n"

        f"📋 No. Pesanan:\n{d['order_id']}\n\n"

        f"📅 Waktu Order:\n{d['time']}\n\n"

        "Mohon menunggu sebentar, USDT akan segera di-release setelah pembayaran terkonfirmasi. 🙏"
    )


# ============================================================
# STATE
# ============================================================

def new_state(
    session_id,
    status,
    direction
):

    return {
        "session_id": str(session_id),
        "direction": direction,
        "first_seen": datetime.now().isoformat(),

        "last_status": status,

        "message_1_sent": False,
        "message_10_sent": False,
        "message_2_sent": False,
        "message_3_sent": False
    }


# ============================================================
# PROCESS EXISTING ORDER
# ============================================================

def process_existing(
    order_id,
    session_id,
    session,
    order,
    messages
):

    order_id = str(order_id)

    direction = get_order_direction(
        order
    )

    if direction not in (
        "BUY",
        "SELL"
    ):

        print(
            f"SKIP {order_id}: "
            f"side tidak dikenali -> "
            f"{order.get('side')}"
        )

        return

    try:
        current = int(
            order.get(
                "realOrderStatus"
            )
        )
    except Exception:
        current = order.get(
            "realOrderStatus"
        )

    if order_id not in state:

        state[order_id] = new_state(
            session_id,
            current,
            direction
        )

        save_state(state)

        return

    s = state[order_id]

    previous = s.get(
        "last_status"
    )

    s["session_id"] = str(
        session_id
    )

    s["direction"] = direction


    # --------------------------------------------------------
    # SELL STATUS 8
    # --------------------------------------------------------

    if (
        direction == "SELL"
        and current == SELL_VERIFY_STATUS
        and not s.get(
            "message_1_sent"
        )
    ):

        print("=" * 60)
        print(
            f"SELL STATUS 8: {order_id}"
        )
        print(
            "Mengirim MESSAGE 1..."
        )
        print("=" * 60)

        if AUTO_SEND:

            if send_message(
                session_id,
                order_id,
                MESSAGE_1
            ):

                s[
                    "message_1_sent"
                ] = True

                print(
                    "MESSAGE 1 TERKIRIM ✅"
                )

        s[
            "last_status"
        ] = current

        save_state(state)

        return


    # --------------------------------------------------------
    # TIDAK ADA PERUBAHAN
    # --------------------------------------------------------

    if current == previous:
        return


    print("=" * 60)
    print(
        f"ORDER BERUBAH: "
        f"{direction} | {order_id}"
    )
    print(
        f"{previous} -> {current}"
    )
    print("=" * 60)


    # --------------------------------------------------------
    # SELL STATUS 10
    # --------------------------------------------------------

    if (
        direction == "SELL"
        and current == NEW_ORDER_STATUS
        and not s.get(
            "message_10_sent"
        )
    ):

        if AUTO_SEND:

            print(
                "Mengirim SELL MESSAGE STATUS 10..."
            )

            if send_message(
                session_id,
                order_id,
                SELL_MESSAGE_10
            ):

                s[
                    "message_10_sent"
                ] = True

                print(
                    "SELL MESSAGE STATUS 10 TERKIRIM ✅"
                )


    # --------------------------------------------------------
    # BUY STATUS 10
    # --------------------------------------------------------

    elif (
        direction == "BUY"
        and current == NEW_ORDER_STATUS
        and not s.get(
            "message_1_sent"
        )
    ):

        if AUTO_SEND:

            message = build_buy_message_1(
                order_id,
                session_id,
                session,
                order,
                messages
            )

            if send_message(
                session_id,
                order_id,
                message
            ):

                s[
                    "message_1_sent"
                ] = True

                print(
                    "MESSAGE 1 TERKIRIM ✅"
                )


    # --------------------------------------------------------
    # STATUS 20
    # --------------------------------------------------------

    elif (
        current == PAID_STATUS
        and not s.get(
            "message_2_sent"
        )
    ):

        if AUTO_SEND:

            if direction == "BUY":

                message = BUY_MESSAGE_2

            else:

                message = build_sell_message_2(
                    order_id,
                    session_id,
                    session,
                    order,
                    messages
                )

            if send_message(
                session_id,
                order_id,
                message
            ):

                s[
                    "message_2_sent"
                ] = True

                print(
                    "MESSAGE 2 TERKIRIM ✅"
                )


    # --------------------------------------------------------
    # STATUS 50
    # --------------------------------------------------------

    elif (
        current == RELEASED_STATUS
        and not s.get(
            "message_3_sent"
        )
    ):

        if AUTO_SEND:

            if direction == "BUY":

                message = BUY_MESSAGE_3

            else:

                message = MESSAGE_3

            if send_message(
                session_id,
                order_id,
                message
            ):

                s[
                    "message_3_sent"
                ] = True

                print(
                    "MESSAGE 3 TERKIRIM ✅"
                )


    s[
        "last_status"
    ] = current

    save_state(state)


# ============================================================
# INITIAL BASELINE
# ============================================================

def initialize_existing_orders():

    print(
        "Memuat session sebagai baseline..."
    )

    total = 0

    sessions = get_sessions()

    session_messages = (
        get_all_session_messages(
            sessions
        )
    )

    all_orders = []

    for session, messages in session_messages:

        sid = session.get(
            "sessionId"
        )

        if not sid:
            continue

        order_ids = extract_order_ids(
            messages
        )

        for oid in order_ids:

            all_orders.append(
                (
                    oid,
                    sid,
                    session,
                    messages
                )
            )

    order_ids = {
        x[0]
        for x in all_orders
        if x[0] not in state
    }

    orders = get_all_order_info(
        order_ids
    )

    for oid, sid, session, messages in all_orders:

        oid = str(oid)

        if oid in state:
            continue

        order = orders.get(oid)

        if not order:
            continue

        direction = get_order_direction(
            order
        )

        if direction not in (
            "BUY",
            "SELL"
        ):
            continue

        try:

            status = int(
                order.get(
                    "realOrderStatus"
                )
            )

        except Exception:

            status = order.get(
                "realOrderStatus"
            )


        # ----------------------------------------------------
        # SELL STATUS 8 & 10 TIDAK DI-BASELINE
        # Supaya order yang sedang berada di 8/10
        # bisa diproses.
        # ----------------------------------------------------

        if (
            direction == "SELL"
            and status in (
                SELL_VERIFY_STATUS,
                NEW_ORDER_STATUS
            )
        ):
            continue


        state[oid] = new_state(
            sid,
            status,
            direction
        )

        total += 1


    save_state(state)

    print(
        f"{total} order lama dijadikan baseline."
    )

    print(
        "Order lama TIDAK mengirim pesan."
    )


# ============================================================
# CHECK ORDERS - FAST
# ============================================================

def check_orders():

    sessions = get_sessions()

    if not sessions:
        return


    # --------------------------------------------------------
    # AMBIL SEMUA CHAT SECARA PARALEL
    # --------------------------------------------------------

    session_messages = (
        get_all_session_messages(
            sessions
        )
    )


    order_context = {}

    for session, messages in session_messages:

        sid = session.get(
            "sessionId"
        )

        if not sid:
            continue

        order_ids = extract_order_ids(
            messages
        )

        for oid in order_ids:

            oid = str(oid)

            order_context[
                oid
            ] = (
                sid,
                session,
                messages
            )


    if not order_context:
        return


    # --------------------------------------------------------
    # AMBIL INFO ORDER SECARA PARALEL
    # --------------------------------------------------------

    order_ids = list(
        order_context.keys()
    )

    orders = get_all_order_info(
        order_ids
    )


    # --------------------------------------------------------
    # PROCESS
    # --------------------------------------------------------

    for oid, order in orders.items():

        sid, session, messages = (
            order_context[oid]
        )


        # ----------------------------------------------------
        # ORDER BARU
        # ----------------------------------------------------

        if oid not in state:

            direction = get_order_direction(
                order
            )

            if direction not in (
                "BUY",
                "SELL"
            ):

                print(
                    f"SKIP {oid}: "
                    f"side tidak dikenali -> "
                    f"{order.get('side')}"
                )

                continue


            try:

                status = int(
                    order.get(
                        "realOrderStatus"
                    )
                )

            except Exception:

                status = order.get(
                    "realOrderStatus"
                )


            print("")
            print(
                f"🆕 ORDER {direction} BARU"
            )
            print(
                f"Order ID : {oid}"
            )
            print(
                f"Status   : {status}"
            )


            state[oid] = new_state(
                sid,
                status,
                direction
            )


            # ------------------------------------------------
            # SELL STATUS 8
            # ------------------------------------------------

            if (
                direction == "SELL"
                and status == SELL_VERIFY_STATUS
                and AUTO_SEND
            ):

                print(
                    "Status 8 -> "
                    "Mengirim MESSAGE 1..."
                )

                if send_message(
                    sid,
                    oid,
                    MESSAGE_1
                ):

                    state[oid][
                        "message_1_sent"
                    ] = True

                    print(
                        "MESSAGE 1 TERKIRIM ✅"
                    )


            # ------------------------------------------------
            # SELL STATUS 10
            # ------------------------------------------------

            elif (
                direction == "SELL"
                and status == NEW_ORDER_STATUS
                and AUTO_SEND
            ):

                print(
                    "Status 10 -> "
                    "Mengirim SELL MESSAGE..."
                )

                if send_message(
                    sid,
                    oid,
                    SELL_MESSAGE_10
                ):

                    state[oid][
                        "message_10_sent"
                    ] = True

                    print(
                        "SELL MESSAGE STATUS 10 "
                        "TERKIRIM ✅"
                    )


            # ------------------------------------------------
            # BUY STATUS 10
            # ------------------------------------------------

            elif (
                direction == "BUY"
                and status == NEW_ORDER_STATUS
                and AUTO_SEND
            ):

                message = build_buy_message_1(
                    oid,
                    sid,
                    session,
                    order,
                    messages
                )

                if send_message(
                    sid,
                    oid,
                    message
                ):

                    state[oid][
                        "message_1_sent"
                    ] = True

                    print(
                        "MESSAGE 1 TERKIRIM ✅"
                    )


            save_state(state)


        # ----------------------------------------------------
        # ORDER LAMA / STATUS BERUBAH
        # ----------------------------------------------------

        else:

            process_existing(
                oid,
                sid,
                session,
                order,
                messages
            )


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 70)
    print(
        "BYBIT P2P BUY + SELL CHAT BOT"
    )
    print(
        "FAST VERSION"
    )
    print("=" * 70)

    print(
        "SELL: 8 -> M1 | 10 -> M10 | 20 -> M2 | 50 -> M3"
    )

    print(
        "BUY : 10 -> M1 | 20 -> M2 | 50 -> M3"
    )

    print(
        "AUTO_SEND :",
        AUTO_SEND
    )

    print(
        "INTERVAL  :",
        CHECK_INTERVAL,
        "detik"
    )

    print(
        "PARALLEL  :",
        MAX_WORKERS,
        "workers"
    )

    print(
        "BASE URL  :",
        BASE_URL
    )

    print(
        "RELEASE   : MANUAL ONLY"
    )

    print(
        "AUTO-RELEASE API: TIDAK ADA"
    )

    print("=" * 70)


    # --------------------------------------------------------
    # BASELINE
    # --------------------------------------------------------

    initialize_existing_orders()


    # --------------------------------------------------------
    # LOOP
    # --------------------------------------------------------

    while True:

        started = time.time()

        try:

            check_orders()

            elapsed = time.time() - started

            print(
                f"[{datetime.now().strftime('%H:%M:%S')}] "
                f"Menunggu... "
                f"(cek: {elapsed:.2f}s)"
            )

            # Kalau API request memakan waktu 1.5 detik,
            # bot tidak perlu menunggu 2 detik penuh lagi.
            remaining = max(
                0,
                CHECK_INTERVAL - elapsed
            )

            time.sleep(
                remaining
            )


        except KeyboardInterrupt:

            print(
                "BOT DIHENTIKAN."
            )

            break


        except Exception as e:

            print(
                "ERROR:",
                e
            )

            time.sleep(2)


# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    main()