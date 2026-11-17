// もしもカード：すべてこのスマホの中だけで処理する（サーバーには何も送らない）
(function () {
  "use strict";
  var KEY = "mamorinet.moshimo-card.v1";
  var form = document.getElementById("card-form");
  var savedEl = document.getElementById("saved");

  // ---------- 保存と読み込み ----------
  function collect() {
    var d = {};
    Array.prototype.forEach.call(form.elements, function (el) {
      if (el.name) d[el.name] = el.value.trim();
    });
    form.querySelectorAll(".checks").forEach(function (box) {
      d[box.dataset.name] = Array.prototype.map.call(box.querySelectorAll("input:checked"), function (c) { return c.value; });
    });
    return d;
  }

  function fill(d) {
    Array.prototype.forEach.call(form.elements, function (el) {
      if (el.name) el.value = typeof d[el.name] === "string" ? d[el.name] : "";
    });
    form.querySelectorAll(".checks").forEach(function (box) {
      var vals = Array.isArray(d[box.dataset.name]) ? d[box.dataset.name] : [];
      box.querySelectorAll("input").forEach(function (c) { c.checked = vals.indexOf(c.value) >= 0; });
    });
  }

  function load() {
    try { return JSON.parse(localStorage.getItem(KEY) || "null"); } catch (e) { return null; }
  }

  function save() {
    var d = collect();
    d.updated = new Date().toISOString().slice(0, 10);
    try {
      localStorage.setItem(KEY, JSON.stringify(d));
      savedEl.textContent = "✓ このスマホに保存しました（" + jpDate(d.updated) + "）";
    } catch (e) {
      savedEl.textContent = "このブラウザでは保存できません。「ファイルに書き出す」を使ってください。";
    }
    return d;
  }

  var timer = null;
  form.addEventListener("input", function () { clearTimeout(timer); timer = setTimeout(save, 400); });
  form.addEventListener("change", save);
  form.addEventListener("submit", function (e) { e.preventDefault(); });

  // ---------- 日付 ----------
  function jpDate(iso) {
    if (!iso) return "";
    var p = iso.split("-");
    return Number(p[0]) + "年" + Number(p[1]) + "月" + Number(p[2]) + "日";
  }
  function addMonths(iso, n) {
    var p = iso.split("-").map(Number);
    var d = new Date(p[0], p[1] - 1 + n, p[2]);
    return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
  }
  function age(birth) {
    if (!birth) return "";
    var b = birth.split("-").map(Number), now = new Date();
    var a = now.getFullYear() - b[0];
    if (now.getMonth() + 1 < b[1] || (now.getMonth() + 1 === b[1] && now.getDate() < b[2])) a--;
    return a >= 0 && a < 130 ? a + "歳" : "";
  }

  // ---------- 印刷用の画面を作る（textContent を使い、入力をそのままHTMLにしない） ----------
  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }
  function join(list, other) {
    var all = (list || []).slice();
    if (other) all.push(other);
    return all.join("、");
  }
  function famLine(d, n) {
    var name = d["fam" + n + "_name"], rel = d["fam" + n + "_rel"], tel = d["fam" + n + "_tel"];
    if (!name && !tel) return "";
    return (name || "") + (rel ? "（" + rel + "）" : "") + (tel ? "　☎ " + tel : "");
  }
  function rows(d) {
    var birth = d.birth ? jpDate(d.birth) + (age(d.birth) ? "（" + age(d.birth) + "）" : "") : "";
    return [
      ["家族の連絡先 1", famLine(d, 1), true],
      ["家族の連絡先 2", famLine(d, 2), true],
      ["生年月日", birth],
      ["かかりつけ", [d.hosp_name, d.hosp_tel ? "☎ " + d.hosp_tel : ""].filter(Boolean).join("　")],
      ["持病", join(d.disease, d.disease_other)],
      ["お薬手帳の場所", d.med_book, true],
      ["特に大事な薬", join(d.med_important, d.med_other)],
      ["アレルギー", join(d.allergy, d.allergy_other)],
      ["マイナ保険証の場所", d.myna],
      ["避難先", [d.shelter, d.evac_help].filter(Boolean).join("　／　")],
      ["生活のこと", join(d.life, d.life_other)],
    ];
  }

  function renderA4(d) {
    var root = document.getElementById("print-a4");
    root.replaceChildren();
    var wrap = el("div", "a4");
    var h = el("h2", null, "もしもカード");
    h.appendChild(el("small", null, "救急隊・避難所の方へ"));
    wrap.appendChild(h);
    wrap.appendChild(el("p", "who", (d.name || "（お名前）") + (d.kana ? "（" + d.kana + "）" : "")));
    var t = el("table");
    rows(d).forEach(function (r) {
      var tr = el("tr", r[2] ? "big" : null);
      tr.appendChild(el("th", null, r[0]));
      tr.appendChild(el("td", null, r[1] || "—"));
      t.appendChild(tr);
    });
    wrap.appendChild(t);
    var foot = el("div", "foot");
    foot.appendChild(el("span", null, "最終更新：" + jpDate(d.updated) + "　／　次の見直し：" + jpDate(addMonths(d.updated, 6)) + "ごろ"));
    foot.appendChild(el("span", null, "にちなん・まもりネット"));
    wrap.appendChild(foot);
    root.appendChild(wrap);
  }

  function renderWallet(d) {
    var root = document.getElementById("print-wallet");
    root.replaceChildren();
    var sheet = el("div", "wallet-sheet");
    for (var i = 0; i < 2; i++) {
      var c = el("div", "wallet");
      var h = el("h3", null, "もしもカード　" + (d.name || ""));
      h.appendChild(el("small", null, "更新 " + jpDate(d.updated)));
      c.appendChild(h);
      var dl = el("dl");
      rows(d).filter(function (r) { return r[1]; }).forEach(function (r) {
        dl.appendChild(el("dt", null, r[0].replace("家族の連絡先 ", "家族")));
        dl.appendChild(el("dd", null, r[1]));
      });
      c.appendChild(dl);
      sheet.appendChild(c);
    }
    root.appendChild(sheet);
  }

  function renderSticker() {
    var root = document.getElementById("print-sticker");
    root.replaceChildren();
    var sheet = el("div", "sticker-sheet");
    for (var i = 0; i < 4; i++) {
      var s = el("div", "sticker");
      s.appendChild(el("div", "s1", "もしもカード"));
      s.appendChild(el("div", "s2", "あります"));
      s.appendChild(el("div", "s3", "救急隊の方へ：冷蔵庫に貼ってあります"));
      sheet.appendChild(s);
    }
    root.appendChild(sheet);
  }

  function prepare(kind) {
    var d = save();
    renderA4(d); renderWallet(d); renderSticker();
    document.body.classList.remove("p-a4", "p-wallet", "p-sticker");
    document.body.classList.add("p-" + kind);
  }

  document.querySelectorAll("[data-print]").forEach(function (b) {
    b.addEventListener("click", function () {
      if (!form.elements.namedItem("name").value.trim() && b.dataset.print !== "sticker") {
        savedEl.textContent = "お名前を入れてください。";
        form.elements.namedItem("name").focus();
        return;
      }
      prepare(b.dataset.print);
      window.print();
    });
  });
  // ブラウザのメニューから印刷したときも A4 を出す
  window.addEventListener("beforeprint", function () {
    if (!document.body.className.match(/p-/)) prepare("a4");
  });
  window.addEventListener("afterprint", function () {
    document.body.classList.remove("p-a4", "p-wallet", "p-sticker");
  });

  // ---------- ファイルに書き出す・読み込む ----------
  document.getElementById("export").addEventListener("click", function () {
    var d = save();
    var blob = new Blob([JSON.stringify({ type: "moshimo-card", version: 1, data: d }, null, 2)], { type: "application/json" });
    var a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "もしもカード_" + (d.name || "未入力") + "_" + d.updated + ".json";
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(function () { URL.revokeObjectURL(a.href); }, 1000);
  });

  document.getElementById("import").addEventListener("change", function (e) {
    var f = e.target.files && e.target.files[0];
    if (!f) return;
    var r = new FileReader();
    r.onload = function () {
      try {
        var obj = JSON.parse(r.result);
        if (!obj || obj.type !== "moshimo-card" || typeof obj.data !== "object") throw new Error("format");
        fill(obj.data);
        save();
        savedEl.textContent = "✓ ファイルを読み込みました";
      } catch (err) {
        savedEl.textContent = "このファイルは読み込めませんでした（もしもカードのファイルを選んでください）。";
      }
      e.target.value = "";
    };
    r.readAsText(f);
  });

  // ---------- すべて消す（2回押して確定） ----------
  var clearBtn = document.getElementById("clear"), armed = false, armTimer;
  clearBtn.addEventListener("click", function () {
    if (!armed) {
      armed = true;
      clearBtn.textContent = "もう一度押すと消えます";
      armTimer = setTimeout(function () { armed = false; clearBtn.textContent = "🗑 すべて消す"; }, 4000);
      return;
    }
    clearTimeout(armTimer);
    armed = false;
    clearBtn.textContent = "🗑 すべて消す";
    try { localStorage.removeItem(KEY); } catch (e) { /* 何もしない */ }
    fill({});
    savedEl.textContent = "すべて消しました。";
  });

  // ---------- 起動 ----------
  var initial = load();
  if (initial) {
    fill(initial);
    savedEl.textContent = "前回の内容を読み込みました（" + jpDate(initial.updated) + " 更新）";
  }
})();
