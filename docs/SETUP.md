# まもりネット 開発・設置・運用ガイド

設計書（[README.md](../README.md)）の v3 を実装したものです。

## フォルダ構成

| 場所 | 中身 | 設計書 |
|---|---|---|
| `app/watch.py` | 見守りの状態遷移（純粋な関数） | 3章 機能①・4-5 |
| `app/quake.py` | 気象庁 防災情報XML の解析・震度判定 | 3章 機能③・4-5 |
| `app/service.py` | LINE イベント処理、5分ごとの見守り判定、地震の安否確認 | 3章 |
| `app/messages.py` | LINE に送る文面（「迷ったら」は案内だけ） | 3章 |
| `app/db.py` | SQLite（**健康情報の列はなし**） | 4-3 |
| `app/line_api.py` | 署名検証・reply/push・ドライラン | 5章 |
| `app/scheduler.py` | 見守り判定（5分）・地震監視（1分）のループ | 4-1 |
| `app/main.py` | FastAPI（`/callback`・`/healthz`） | 4-1 |
| `app/admin.py` | 管理コマンド（評価指標の集計など） | 7章 |
| `static/card/` | もしもカード（HTML+JS のみ。通信を CSP で禁止） | 3章 機能② |
| `static/data/` | データで見る日南（グラフ・表） | 3章 機能④ |
| `static/terms/` | 利用のきまり・個人情報の扱い | 5章 |
| `scripts/richmenu.py` | リッチメニューの画像作成・登録 | 3章 機能① |
| `deploy/` | Nginx・systemd・設置スクリプト・S3 バックアップ | 4-1・4-4 |
| `tests/` | pytest（状態遷移・震度判定・全体の流れ・Webhook） | 7章 |

## 1. 手元で動かす（LINE の鍵なしで OK）

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
pytest -q                                   # すべて合格することを確認
uvicorn app.main:app --reload               # http://localhost:8000/card/ など
```

`LINE_CHANNEL_ACCESS_TOKEN` が空のときは **ドライラン**：LINE には送らず、送るはずだった内容を
`outbox` テーブルに残します（`python -m app.admin outbox` で確認）。

## 2. LINE 公式アカウントの準備

1. LINE Developers でプロバイダー（学校名義にするか先生と相談）と **Messaging API チャネル**を作る
2. 「チャネルシークレット」と「チャネルアクセストークン（長期）」を `.env` に書く（`.env.example` を参照。**Git に入れない**）
3. LINE Official Account Manager で「応答メッセージ」をオフ、「Webhook」をオンにする
4. Webhook URL に `https://<ドメイン>/callback` を設定し「検証」
5. リッチメニューを登録：
   ```bash
   pip install pillow
   python scripts/richmenu.py make-image richmenu.png
   python scripts/richmenu.py upload richmenu.png
   ```

## 3. AWS Academy（EC2・Ubuntu Server 26.04 LTS）に設置

- セキュリティグループ：22（自分のIPのみ・鍵認証）、80・443（全体）
- IAM ロール：LabInstanceProfile（S3 バックアップ用）

```bash
git clone <このリポジトリ> ~/mamorinet && cd ~/mamorinet
sudo EMAIL=<先生の連絡用アドレス> bash deploy/setup.sh   # DOMAIN を省くと <IP>.sslip.io を使う
sudo nano /opt/mamorinet/.env                          # LINE の鍵を入れる
sudo systemctl restart mamorinet
```

**Learner Lab は再起動のたびに IP が変わる**ので、そのたびに `setup.sh` を再実行し、
LINE の Webhook URL を新しい sslip.io の名前に直す（Elastic IP が使えればその必要なし）。

バックアップ（毎日・暗号化して S3 へ）：
```bash
sudo crontab -e
15 3 * * * MAMORI_BACKUP_BUCKET=s3://<バケット名> /opt/mamorinet/deploy/backup.sh >> /var/log/mamorinet-backup.log 2>&1
```

## 4. 使い方（LINE のトーク）

| 送る文字 | だれが | 動き |
|---|---|---|
| （友だち追加） | 全員 | 説明と「本人／家族」の選択。押すと同意日時を記録 |
| メニュー「げんき！」 | 本人 | その日の見守り完了。返信は**応答メッセージ（無料）** |
| 6けたの数字 | 家族 | 招待コードで本人とつながる（第1→第2の順、2人まで） |
| 設定 | 全員 | 時刻・お休み・連絡先を表示 |
| 時刻 10:00 11:00 13:00 | 本人・家族 | 再通知・家族通知・第2通知の時刻 |
| お休み 11/20-11/22 ／ お休み解除 | 本人・家族 | 旅行・入院など |
| 電話 09012345678 | 全員 | 「電話する」ボタン用の番号 |
| 名前 ○○ | 全員 | 呼び名 |
| 迷ったら | 全員 | 119・日南市救急医療電話相談・Q助への案内（判定しない） |
| 「きつい」「転んだ」など | 本人 | 家族にすぐ知らせる（優先度を上げるだけで、下げない） |
| 登録解除（またはブロック） | 全員 | 記録とつながりを削除 |

### 設計書から補った点
- **登録した日の誤報を防ぐ**：再通知時刻を過ぎてから登録・つながった場合、見守りは翌日から。
- **サーバー停止明け**：1回の確認で1段階しか進まないので、いきなり家族へ通知せず、まず本人に再通知する。
- **家族通知のあとに「げんき」**：未確認の家族に「○時に押しました」と知らせる。
- **第2連絡先がいない**：13時の通知は第1連絡先にもう一度送る。
- **地震**：訓練・試験・取消の電文は無視。「震度５弱以上未入電」は安全側で送る。3時間より古い電文は送らない（再起動直後の誤送信防止）。同じ地震IDの続報では送らない。

## 5. 実証実験の運用（設計書 7章）

```bash
cd /opt/mamorinet && sudo -u mamorinet .venv/bin/python -m app.admin users
sudo -u mamorinet .venv/bin/python -m app.admin report --from 2026-11-27 --to 2026-12-06
```

`report` で出る数字：げんきを押した日の割合（目標80%）、設定時刻の前に押した割合（目標90%）、
家族に通知した日、**誤報の候補**（家族に通知したあとで本人がげんきを押した日）、プッシュ通数（月200通の目安）。

地震の動作確認（実際には送らず、記録も残さない）：
```bash
python -m app.admin quake tests/fixtures/vxse53_nichinan_5minus.xml
```

「わざと押さない日」のテストは、その日に何もしなければ時刻どおりに通知が届きます。

実証実験の終了後：`python -m app.admin purge --yes` と S3 のバックアップ削除。

## 6. 応募前に確認すること

- 気象庁の日南市コード `4520400`（気象庁「市町村等（地震情報）」コード表。実際の電文で球磨村 `4351300` の形式を確認済み）
- Q助のURL（`app/config.py`。2026年11月に表示を確認）、避難所案内のURL（`.env` の `MAMORI_SHELTER_URL`）
- 「迷ったら」の文言を消防本部・市の案内に合わせる（`app/messages.py`）
- LINE の料金プラン（無料メッセージ通数）
- `tests/fixtures/vxse53_other_city.xml` は気象庁の実物、それ以外は実物の形式をまねた**テスト用データ**
