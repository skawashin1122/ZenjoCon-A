// データで見る日南：ミニ統計の数値（README 1-1 の表と同じ）。外部ライブラリは使わない
(function () {
  "use strict";
  var NS = "http://www.w3.org/2000/svg";
  var tip = document.getElementById("tip");
  var fmt = function (n, d) { return Number(n).toLocaleString("ja-JP", { minimumFractionDigits: d || 0, maximumFractionDigits: d || 0 }); };

  var AMB = [
    { k: "令和3年", v: 2321, pop: 49853 },
    { k: "令和4年", v: 2707, pop: 48956 },
    { k: "令和5年", v: 2984, pop: 47949 },
    { k: "令和6年", v: 2802, pop: 47166 },
    { k: "令和7年", v: 2805, pop: 45895, note: "人口は国勢調査速報" },
  ];
  AMB.forEach(function (d) { d.rate = Math.round(d.v / d.pop * 10000) / 10; });
  var BEDS = [
    { k: "R3.12.31", v: 1260, h: 9 },
    { k: "R4.10.1", v: 1213, h: 8 },
    { k: "R5.10.1", v: 1122, h: 7 },
  ];
  var DIST = [
    { k: "吾田", a: 17614, b: 17181, hh: 2.17 },
    { k: "東郷", a: 4510, b: 4297, hh: 2.54 },
    { k: "飫肥", a: 5305, b: 5030, hh: 2.31 },
    { k: "北郷", a: 3755, b: 3483, hh: 2.37 },
    { k: "南郷", a: 8378, b: 7616, hh: 2.17 },
    { k: "鵜戸", a: 657, b: 594, hh: 1.89 },
    { k: "酒谷", a: 749, b: 675, hh: 1.89 },
    { k: "油津", a: 4576, b: 4107, hh: 1.88 },
    { k: "細田", a: 2746, b: 2449, hh: 1.89 },
  ];
  DIST.forEach(function (d) { d.rate = Math.round((d.b - d.a) / d.a * 1000) / 10; });
  DIST.sort(function (x, y) { return x.rate - y.rate; });

  function svg(tag, attrs, parent) {
    var e = document.createElementNS(NS, tag);
    for (var k in attrs) e.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(e);
    return e;
  }
  function text(parent, x, y, s, attrs) {
    var t = svg("text", Object.assign({ x: x, y: y }, attrs || {}), parent);
    t.textContent = s;
    return t;
  }
  // 上だけ角丸（4px）・根元は四角の棒
  function colPath(x, y, w, h) {
    var r = Math.min(4, h, w / 2);
    return "M" + x + "," + (y + h) + "V" + (y + r) + "Q" + x + "," + y + " " + (x + r) + "," + y +
      "H" + (x + w - r) + "Q" + (x + w) + "," + y + " " + (x + w) + "," + (y + r) + "V" + (y + h) + "Z";
  }
  // 右だけ角丸の横棒
  function barPath(x, y, w, h) {
    var r = Math.min(4, w, h / 2);
    return "M" + x + "," + y + "H" + (x + w - r) + "Q" + (x + w) + "," + y + " " + (x + w) + "," + (y + r) +
      "V" + (y + h - r) + "Q" + (x + w) + "," + (y + h) + " " + (x + w - r) + "," + (y + h) + "H" + x + "Z";
  }
  function showTip(ev, html) {
    tip.innerHTML = html;
    tip.hidden = false;
    var x = ev.clientX + 14, y = ev.clientY + 14;
    var w = tip.offsetWidth, h = tip.offsetHeight;
    if (x + w > window.innerWidth - 8) x = ev.clientX - w - 14;
    if (y + h > window.innerHeight - 8) y = ev.clientY - h - 14;
    tip.style.left = x + "px"; tip.style.top = y + "px";
  }
  function hideTip() { tip.hidden = true; }
  function hover(el, html) {
    el.addEventListener("pointermove", function (e) { showTip(e, html); });
    el.addEventListener("pointerleave", hideTip);
  }
  function niceMax(v) {
    var p = Math.pow(10, Math.floor(Math.log10(v))), n = v / p;
    return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10) * p;
  }
  function table(card, head, rows) {
    var det = document.createElement("details");
    det.innerHTML = "<summary>表で見る</summary>";
    var wrap = document.createElement("div"); wrap.className = "table-wrap";
    var t = document.createElement("table");
    var tr = t.insertRow();
    head.forEach(function (h) { var th = document.createElement("th"); th.textContent = h; tr.appendChild(th); });
    rows.forEach(function (r) { var row = t.insertRow(); r.forEach(function (c) { row.insertCell().textContent = c; }); });
    wrap.appendChild(t); det.appendChild(wrap);
    card.insertBefore(det, card.querySelector(".src"));
  }

  // ---------- 縦棒 ----------
  function columns(id, data, opt) {
    var card = document.getElementById(id), host = card.querySelector(".chart");
    var W = Math.max(360, Math.min(720, host.clientWidth || 720)), H = 280, L = 52, R = 12, T = 24, B = 32;
    var s = svg("svg", { viewBox: "0 0 " + W + " " + H }, host);
    var max = niceMax(Math.max.apply(null, data.map(function (d) { return d.v; })) * 1.05);
    var y = function (v) { return T + (H - T - B) * (1 - v / max); };
    for (var i = 0; i <= 4; i++) {
      var gv = max / 4 * i;
      svg("line", { x1: L, x2: W - R, y1: y(gv), y2: y(gv), class: "grid" }, s);
      text(s, L - 8, y(gv) + 4, fmt(gv), { "text-anchor": "end" });
    }
    var band = (W - L - R) / data.length, bw = Math.min(24, band * 0.5);
    var peak = data.reduce(function (a, d) { return d.v > a.v ? d : a; }, data[0]);
    data.forEach(function (d, i) {
      var cx = L + band * i + band / 2, top = y(d.v);
      var g = svg("g", {}, s);
      svg("path", { d: colPath(cx - bw / 2, top, bw, y(0) - top), fill: "var(--series-1)", class: "mark" }, g);
      text(s, cx, H - 10, d.k, { "text-anchor": "middle" });
      if (d === peak || i === 0 || i === data.length - 1) {
        text(s, cx, top - 6, fmt(d.v) + (opt.unit || ""), { "text-anchor": "middle", class: "val" });
      }
      var hit = svg("rect", { x: L + band * i, y: T, width: band, height: H - T - B, class: "hit" }, s);
      hover(hit, opt.tip(d));
    });
  }

  // ---------- 折れ線 ----------
  function line(id, data, opt) {
    var card = document.getElementById(id), host = card.querySelector(".chart");
    var W = Math.max(360, Math.min(720, host.clientWidth || 720)), H = 260, L = 52, R = 40, T = 24, B = 32;
    var s = svg("svg", { viewBox: "0 0 " + W + " " + H }, host);
    var max = 70;
    var y = function (v) { return T + (H - T - B) * (1 - v / max); };
    var x = function (i) { return L + 20 + (W - L - R - 40) * i / (data.length - 1); };
    for (var g = 0; g <= max; g += 10) {
      svg("line", { x1: L, x2: W - R, y1: y(g), y2: y(g), class: "grid" }, s);
      if (g % 20 === 0) text(s, L - 8, y(g) + 4, fmt(g), { "text-anchor": "end" });
    }
    var dPath = data.map(function (d, i) { return (i ? "L" : "M") + x(i) + "," + y(d.rate); }).join("");
    svg("path", { d: dPath + "L" + x(data.length - 1) + "," + y(0) + "L" + x(0) + "," + y(0) + "Z",
      fill: "var(--series-1)", "fill-opacity": 0.1 }, s);
    svg("path", { d: dPath, fill: "none", stroke: "var(--series-1)", "stroke-width": 2,
      "stroke-linejoin": "round", "stroke-linecap": "round" }, s);
    var cross = svg("line", { y1: T, y2: H - B, stroke: "var(--text-muted)", "stroke-width": 1, visibility: "hidden" }, s);
    data.forEach(function (d, i) {
      svg("circle", { cx: x(i), cy: y(d.rate), r: 4.5, fill: "var(--series-1)", stroke: "var(--surface-1)", "stroke-width": 2 }, s);
      text(s, x(i), H - 10, d.k, { "text-anchor": "middle" });
      if (i === 0 || i === data.length - 1 || d.rate === Math.max.apply(null, data.map(function (e) { return e.rate; }))) {
        text(s, x(i), y(d.rate) - 12, fmt(d.rate, 1) + "件", { "text-anchor": "middle", class: "val" });
      }
      var half = (x(1) - x(0)) / 2;
      var hit = svg("rect", { x: x(i) - half, y: T, width: half * 2, height: H - T - B, class: "hit" }, s);
      hit.addEventListener("pointermove", function (e) {
        cross.setAttribute("x1", x(i)); cross.setAttribute("x2", x(i)); cross.setAttribute("visibility", "visible");
        showTip(e, opt.tip(d));
      });
      hit.addEventListener("pointerleave", function () { cross.setAttribute("visibility", "hidden"); hideTip(); });
    });
  }

  // ---------- 横棒（減少率） ----------
  function hbars(id, data) {
    var card = document.getElementById(id), host = card.querySelector(".chart");
    var rowH = 30, T = 8, L = 56, R = 64, W = Math.max(360, Math.min(720, host.clientWidth || 720)), H = T + rowH * data.length + 24;
    var s = svg("svg", { viewBox: "0 0 " + W + " " + H }, host);
    var max = 12;
    var x = function (v) { return L + (W - L - R) * v / max; };
    for (var g = 0; g <= max; g += 2) {
      svg("line", { x1: x(g), x2: x(g), y1: T, y2: H - 22, class: "grid" }, s);
      text(s, x(g), H - 6, g === 0 ? "0%" : "−" + g + "%", { "text-anchor": "middle" });
    }
    data.forEach(function (d, i) {
      var yy = T + rowH * i, bh = 20, dec = -d.rate;
      var low = d.hh < 2;
      svg("path", { d: barPath(x(0), yy + (rowH - bh) / 2, x(dec) - x(0), bh),
        fill: low ? "var(--series-2)" : "var(--series-1)", class: "mark" }, s);
      text(s, L - 8, yy + rowH / 2 + 4, d.k, { "text-anchor": "end" });
      text(s, x(dec) + 6, yy + rowH / 2 + 4, fmt(d.rate, 1) + "%", { class: "val" });
      var hit = svg("rect", { x: 0, y: yy, width: W, height: rowH, class: "hit" }, s);
      hover(hit, "<b>" + d.k + "</b><br>人口 " + fmt(d.a) + " → " + fmt(d.b) + "人<br>増減率 <b>" + fmt(d.rate, 1) +
        "%</b><br>1世帯あたり <b>" + d.hh.toFixed(2) + "人</b>");
    });
  }

  columns("c-ambulance", AMB, {
    unit: "件",
    tip: function (d) { return "<b>" + d.k + "</b><br>出動 <b>" + fmt(d.v) + "件</b>"; },
  });
  table(document.getElementById("c-ambulance"), ["年（暦年）", "出動件数"], AMB.map(function (d) { return [d.k, fmt(d.v)]; }));

  line("c-per1000", AMB, {
    tip: function (d) {
      return "<b>" + d.k + "</b><br>千人あたり <b>" + fmt(d.rate, 1) + "件</b><br>出動 " + fmt(d.v) + "件／人口 " + fmt(d.pop) + "人" +
        (d.note ? "<br>※" + d.note : "");
    },
  });
  table(document.getElementById("c-per1000"), ["年", "出動件数", "人口（10/1）", "千人あたり"],
    AMB.map(function (d) { return [d.k, fmt(d.v), fmt(d.pop), fmt(d.rate, 1)]; }));

  columns("c-beds", BEDS, {
    unit: "床",
    tip: function (d) { return "<b>" + d.k + " 時点</b><br>病院 " + d.h + "施設<br>病床 <b>" + fmt(d.v) + "床</b>"; },
  });
  table(document.getElementById("c-beds"), ["調査時点", "病院", "病床"], BEDS.map(function (d) { return [d.k, d.h + "施設", fmt(d.v) + "床"]; }));

  hbars("c-district", DIST);
  table(document.getElementById("c-district"), ["地区", "R5.4.1", "R8.4.1", "増減率", "1世帯あたり人数（R8）"],
    DIST.map(function (d) { return [d.k, fmt(d.a), fmt(d.b), fmt(d.rate, 1) + "%", d.hh.toFixed(2)]; }));
})();
