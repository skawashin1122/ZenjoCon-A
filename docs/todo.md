# 今後の実施手順

にちなん・まもりネット v3 の本番導入に向けた作業チェックリストです。
アプリ本体のテストは完了していますが、LINE・AWS・実機を使った確認は未実施です。

## 0. 事前確認

- [ ] LINEのチャネルシークレットとアクセストークンを準備する
- [ ] AWS AcademyのEC2、キーペア、S3バケットを準備する
- [ ] 学校・先生・関係者と、利用規約、個人情報の扱い、案内文、電話番号を確認する
- [ ] 本番用の本人アカウントと家族アカウントを決める
- [ ] 秘密情報をGit、チャット、スクリーンショットに含めない

## 1. ローカル最終確認

```bash
cd /workspaces/ZenjoCon-A
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
pytest -q
```

- [x] 全テストが成功する（64 passed、2026-11-21確認）
- [x] FastAPIアプリをTestClientで起動して確認する

```bash
uvicorn app.main:app --reload
```

- [x] `/healthz` が`ok: true`を返す（HTTP 200、2026-11-21確認）
- [x] `/`、`/card/`、`/data/`、`/terms/`がHTTP 200を返す（2026-11-21確認）

## 2. LINE公式アカウント設定

- [ ] LINE Developersでプロバイダーを作成する
- [ ] Messaging APIチャネルを作成する
- [ ] チャネルシークレットを取得する
- [ ] 長期チャネルアクセストークンを発行する
- [ ] LINE Official Account Managerで応答メッセージをオフにする
- [ ] Webhookをオンにする
- [ ] Webhook URLはAWS設置後に設定する（ローカルURLは使用しない）

## 3. リッチメニュー登録

`.env`を作成し、アクセストークンを設定する。

```bash
cp .env.example .env
chmod 600 .env
```

```env
LINE_CHANNEL_SECRET=チャネルシークレット
LINE_CHANNEL_ACCESS_TOKEN=チャネルアクセストークン
MAMORI_PUBLIC_URL=https://本番ドメイン
```

- [ ] Pillowをインストールする

```bash
pip install pillow
```

- [ ] リッチメニュー画像を作成する

```bash
python scripts/richmenu.py make-image richmenu.png
```

- [ ] LINEへ登録する

```bash
python scripts/richmenu.py upload richmenu.png
```

- [ ] 「げんき！」「家族に電話」「迷ったら」が表示される

## 4. AWS EC2準備

- [ ] Ubuntu ServerのEC2を作成する
- [ ] セキュリティグループを設定する
  - [ ] 22番：自分のIPアドレスのみ
  - [ ] 80番：全体
  - [ ] 443番：全体
- [ ] EC2にIAMロールを割り当てる
- [ ] IAMロールにS3バックアップ権限を付与する
- [ ] 必要ならElastic IPを割り当てる

```bash
ssh -i 鍵ファイル.pem ubuntu@EC2のIPアドレス
```

## 5. AWSへ設置

EC2上で実行する。

```bash
sudo apt update
sudo apt install -y git
git clone リポジトリURL ~/mamorinet
cd ~/mamorinet
sudo EMAIL=先生のメールアドレス bash deploy/setup.sh
```

固定ドメインを指定する場合：

```bash
sudo DOMAIN=203-0-113-10.sslip.io \
  EMAIL=先生のメールアドレス \
  bash deploy/setup.sh
```

- [ ] `/opt/mamorinet`に配置される
- [ ] Python仮想環境と依存パッケージが作成される
- [ ] Nginxが設定される
- [ ] systemdサービスが起動する
- [ ] Let's Encrypt証明書が発行される

## 6. 本番環境設定

```bash
sudo nano /opt/mamorinet/.env
```

最低限、以下を設定する。

```env
LINE_CHANNEL_SECRET=実際のチャネルシークレット
LINE_CHANNEL_ACCESS_TOKEN=実際のアクセストークン
MAMORI_PUBLIC_URL=https://本番ドメイン
MAMORI_CITY_CODE=4520400
MAMORI_QUAKE_THRESHOLD=5-
MAMORI_QUAKE_ENABLED=1
```

- [ ] 必要に応じて`MAMORI_SHELTER_URL`を設定する
- [ ] `.env`の権限が600になっている
- [ ] アクセストークンが空でない
- [ ] サービスを再起動する

```bash
sudo systemctl restart mamorinet
sudo systemctl status mamorinet --no-pager
```

## 7. HTTPS・Webhook確認

```bash
curl https://本番ドメイン/healthz
sudo journalctl -u mamorinet -n 100 --no-pager
```

- [ ] `/healthz`が`{"ok":true,"dry_run":false}`を返す
- [ ] systemdが`active (running)`になっている
- [ ] エラーログが出ていない

LINE Developersで以下を設定する。

```text
https://本番ドメイン/callback
```

- [ ] Webhookを有効にする
- [ ] 「検証」が成功する

## 8. LINE実機テスト

テスト用の本人・家族アカウントで確認する。

### 登録・連携

- [ ] 友だち追加時に案内が届く
- [ ] 「本人」を選択できる
- [ ] 「家族」を選択できる
- [ ] 本人に6桁の招待コードが発行される
- [ ] 家族が招待コードで連携できる
- [ ] 第1・第2連絡先が正しい順番になる
- [ ] 3人目の家族が登録できない

### 見守り

- [ ] 「げんき！」で当日の状態が完了になる
- [ ] 「げんき！」を押した日は家族通知が発生しない
- [ ] 再通知時刻に本人へ通知される
- [ ] 第1連絡先へ通知される
- [ ] 第2連絡先へ通知される
- [ ] 家族の「確認できた」で次の通知が止まる
- [ ] お休み期間中は通知されない
- [ ] 翌日には状態がリセットされる

### 設定・案内

- [ ] `設定`が表示される
- [ ] `時刻 8:30 9:30 12:00`が反映される
- [ ] `お休み 11/20-11/22`が反映される
- [ ] `お休み解除`が反映される
- [ ] `電話 09012345678`が反映される
- [ ] `名前 ○○`が反映される
- [ ] `迷ったら`が119・救急医療電話相談・Q助を案内する
- [ ] 「転んだ」「きつい」などで家族に通知される
- [ ] 登録解除でユーザーと関連記録が削除される

## 9. 地震機能確認

最初は実送信せず、ドライランで確認する。

```bash
cd /opt/mamorinet
sudo -u mamorinet .venv/bin/python \
  -m app.admin quake tests/fixtures/vxse53_nichinan_5minus.xml
sudo -u mamorinet .venv/bin/python \
  -m app.admin outbox
```

- [ ] 震度5弱のテスト電文が解析される
- [ ] 送信内容が`outbox`に記録される
- [ ] `--yes`を付けない限り実際のLINE送信が行われない
- [ ] 訓練・取消・対象外地域の電文を無視する
- [ ] 同じ地震IDの続報を重複送信しない

## 10. S3バックアップ

- [ ] S3バケットを作成する
- [ ] EC2のIAMロールから書き込めることを確認する
- [ ] 手動バックアップを実行する

```bash
sudo MAMORI_BACKUP_BUCKET=s3://バケット名 \
  bash /opt/mamorinet/deploy/backup.sh
```

- [ ] S3にバックアップファイルが作成される
- [ ] cronを登録する

```bash
sudo crontab -e
```

```cron
15 3 * * * MAMORI_BACKUP_BUCKET=s3://バケット名 /opt/mamorinet/deploy/backup.sh >> /var/log/mamorinet-backup.log 2>&1
```

- [ ] 翌日のバックアップ成功を確認する
- [ ] バックアップログにエラーがない

## 11. 運用開始後の確認

登録者一覧：

```bash
sudo -u mamorinet /opt/mamorinet/.venv/bin/python \
  -m app.admin users
```

評価レポート：

```bash
sudo -u mamorinet /opt/mamorinet/.venv/bin/python \
  -m app.admin report --from YYYY-MM-DD --to YYYY-MM-DD
```

- [ ] げんきを押した日の割合を確認する
- [ ] 設定時刻前に押した割合を確認する
- [ ] 家族通知日数を確認する
- [ ] 誤報候補を確認する
- [ ] 月間プッシュ通数を確認する
- [ ] `systemctl status mamorinet`を定期確認する
- [ ] `journalctl -u mamorinet`で異常を確認する

## 12. AWS Academy再起動時

Learner Labの再起動でIPが変わった場合：

- [ ] 新しいIPを確認する
- [ ] `setup.sh`を再実行する
- [ ] 新しい`sslip.io`ドメインを確認する
- [ ] `.env`の`MAMORI_PUBLIC_URL`を更新する
- [ ] LINE Webhook URLを更新する
- [ ] HTTPS証明書を確認する
- [ ] `/healthz`とWebhook検証を再実施する

## 完了条件

- [ ] 全テストが成功している
- [ ] `/healthz`が正常応答する
- [ ] systemdサービスが稼働している
- [ ] LINE実機で登録から通知まで確認できている
- [ ] 地震機能をドライランで確認している
- [ ] S3バックアップが定期実行されている
- [ ] 関係者が利用規約・案内文・電話番号を確認している
