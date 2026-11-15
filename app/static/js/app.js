const $ = (s) => document.querySelector(s);
const fmt = (n) => Math.round(n).toLocaleString("es-BO");
const COLORES = ["#0f5c6e", "#e0a526", "#b4452f", "#4d8f5b", "#6b5ca5", "#2f8fbf", "#8a6d3b", "#c05a8c", "#555", "#9bb"];
const get = (url) => fetch(url).then((r) => r.json());
const charts = {};
function dibujar(id, config) {
  charts[id]?.destroy();
  charts[id] = new Chart($("#" + id), config);
}
const opciones = (arr, sel) => arr.map((v) => `<option ${v == sel ? "selected" : ""}>${v}</option>`).join("");
const ejes = { y: { ticks: { callback: (v) => fmt(v) } } };

const paginas = {
  async panel() {
    const meta = await get("/api/meta");
    const k = await get("/api/kpis");
    $("#kpis").innerHTML = [
      [fmt(k.total) + " t", `Recolectado en ${k.anio}`],
      [(k.variacion * 100).toFixed(1) + " %", `Variación vs ${k.anio - 1}`],
      [k.ciudad_top, `Ciudad con más residuos (${fmt(k.ciudad_top_ton)} t)`],
      [k.mes_pico, `Mes pico de ${k.anio} (${fmt(k.mes_pico_ton)} t)`],
    ].map(([a, b]) => `<div class="kpi"><b>${a}</b><span>${b}</span></div>`).join("");
    $("#ciudad").innerHTML = opciones(["Total", ...meta.ciudades]);
    $("#desde").innerHTML = opciones(meta.anios, 2005);
    $("#hasta").innerHTML = opciones(meta.anios, meta.anios.at(-1));
    $("#anioRank").innerHTML = opciones(meta.anios, k.anio);
    const serie = async () => {
      const [s] = await get(`/api/serie?cats=${$("#ciudad").value}&desde=${$("#desde").value}&hasta=${$("#hasta").value}&agg=${$("#agg").value}`);
      dibujar("serie", { type: "line", data: { labels: s.x, datasets: [{ label: s.nombre + " (t)", data: s.y, borderColor: COLORES[0], pointRadius: 0, tension: .2 }] }, options: { scales: ejes } });
    };
    const rank = async () => {
      const r = await get("/api/ranking?anio=" + $("#anioRank").value);
      dibujar("ranking", { type: "bar", data: { labels: r.labels, datasets: [{ label: "Toneladas", data: r.values, backgroundColor: COLORES[0] }] }, options: { indexAxis: "y", plugins: { legend: { display: false } } } });
    };
    ["ciudad", "desde", "hasta", "agg"].forEach((i) => $("#" + i).addEventListener("change", serie));
    $("#anioRank").addEventListener("change", rank);
    const c = await get("/api/composicion");
    dibujar("composicion", { type: "bar", data: { labels: c.anios, datasets: Object.entries(c.series).map(([n, y], i) => ({ label: n, data: y, backgroundColor: COLORES[i] })) }, options: { scales: { x: { stacked: true }, y: { stacked: true, ticks: { callback: fmt } } } } });
    serie(); rank();
  },
  async comparar() {
    const meta = await get("/api/meta");
    $("#chips").innerHTML = meta.ciudades.map((c, i) => `<label><input type="checkbox" value="${c}" ${i < 3 ? "checked" : ""}>${c}</label>`).join("");
    const comparar = async () => {
      const cats = [...document.querySelectorAll("#chips input:checked")].map((i) => i.value);
      if (!cats.length) return;
      const data = await get(`/api/serie?cats=${cats.join(",")}&agg=${$("#agg").value}`);
      dibujar("comparar", { type: "line", data: { labels: data[0].x, datasets: data.map((s, i) => ({ label: s.nombre, data: s.y, borderColor: COLORES[i % 10], pointRadius: 0 })) }, options: { scales: ejes } });
    };
    $("#chips").addEventListener("change", comparar); $("#agg").addEventListener("change", comparar);
    $("#hmCiudad").innerHTML = opciones(["Total", ...meta.ciudades]);
    const hm = async () => {
      const h = await get("/api/heatmap?cat=" + $("#hmCiudad").value);
      const v = h.valores.flat().filter((x) => x != null), mn = Math.min(...v), mx = Math.max(...v);
      const celda = (x) => x == null ? "<td></td>" : `<td style="background:rgba(15,92,110,${(.1 + .8 * (x - mn) / (mx - mn)).toFixed(2)});color:${(x - mn) / (mx - mn) > .55 ? "#fff" : "#14232b"}">${fmt(x)}</td>`;
      $("#heatmap").innerHTML = `<table class="hm"><tr><th></th>${h.meses.map((m) => `<th>${m}</th>`).join("")}</tr>` + h.anios.map((a, i) => `<tr><th>${a}</th>${h.valores[i].map(celda).join("")}</tr>`).join("") + "</table>";
    };
    $("#hmCiudad").addEventListener("change", hm);
    comparar(); hm();
  },
  async pronostico() {
    const meta = await get("/api/meta");
    $("#ciudad").innerHTML = opciones(["Total", ...meta.ciudades]);
    const run = async () => {
      $("#metodo").textContent = "Calculando…";
      const p = await get(`/api/pronostico?cat=${$("#ciudad").value}&meses=${$("#meses").value}`);
      $("#metodo").textContent = "Método: " + p.metodo;
      const pad = new Array(p.hist.x.length).fill(null);
      dibujar("pronostico", { type: "line", data: { labels: [...p.hist.x, ...p.pred.x], datasets: [
        { label: "Histórico", data: [...p.hist.y, ...new Array(p.pred.x.length).fill(null)], borderColor: COLORES[0], pointRadius: 0 },
        { label: "Pronóstico", data: [...pad, ...p.pred.y], borderColor: COLORES[1], borderDash: [6, 4], pointRadius: 0 },
        { label: "Mínimo", data: [...pad, ...p.pred.min], borderColor: "#e0a52666", pointRadius: 0, fill: "+1", backgroundColor: "#e0a52622" },
        { label: "Máximo", data: [...pad, ...p.pred.max], borderColor: "#e0a52666", pointRadius: 0 }] }, options: { scales: ejes } });
    };
    $("#ciudad").addEventListener("change", run); $("#meses").addEventListener("change", run);
    run();
  },
  async calidad() {
    const f = await get("/api/faltantes");
    const celda = (x) => `<td style="background:${x ? `rgba(180,69,47,${.2 + x / 12 * .8})` : "#e6efe9"};color:${x > 6 ? "#fff" : "#14232b"}">${x || ""}</td>`;
    $("#faltantes").innerHTML = `<table class="hm"><tr><th></th>${f.anios.map((a) => `<th>${a}</th>`).join("")}</tr>` + f.ciudades.map((c, i) => `<tr><th>${c}</th>${f.valores[i].map(celda).join("")}</tr>`).join("") + "</table>";
    const s = await get("/api/imputacion?ciudad=Sucre");
    dibujar("imputacion", { type: "line", data: { labels: s.x, datasets: [
      { label: "Sucre (t)", data: s.y, borderColor: COLORES[0], pointRadius: 0 },
      { label: "Estimado", data: s.y.map((v, i) => s.estimado[i] ? v : null), borderColor: COLORES[1], pointBackgroundColor: COLORES[1], pointRadius: 3, showLine: false }] }, options: { scales: ejes } });
  },
};
const tabla = (cols, filas, color) => `<table class="hm"><tr><th></th>${cols.map((c) => `<th>${c}</th>`).join("")}</tr>` + filas.map(([n, v]) => `<tr><th>${n}</th>${v.map(color).join("")}</tr>`).join("") + "</table>";
const llenarCiudades = async (id = "ciudad", def = "Total") => { const m = await get("/api/meta"); $("#" + id).innerHTML = opciones([def, ...m.ciudades]); return m; };

Object.assign(paginas, {
  async mapa() {
    const [m, geo] = await Promise.all([get("/api/meta"), get("/static/data/bolivia.json")]);
    $("#anio").innerHTML = opciones(m.anios, 2025);

    const W = 520, H = 560, pad = 18;
    const [minLon, minLat, maxLon, maxLat] = geo.bbox;
    const esc = Math.min((W - 2 * pad) / (maxLon - minLon), (H - 2 * pad) / (maxLat - minLat));
    const offX = pad + (W - 2 * pad - (maxLon - minLon) * esc) / 2;
    const offY = pad + (H - 2 * pad - (maxLat - minLat) * esc) / 2;
    const X = (lon) => offX + (lon - minLon) * esc;
    const Y = (lat) => offY + (maxLat - lat) * esc;

    const dDepto = (d) => d.anillos.map((a) =>
      "M" + a.map(([lon, lat]) => X(lon).toFixed(1) + "," + Y(lat).toFixed(1)).join("L") + "Z").join("");
    const trazos = geo.departamentos.map(dDepto);
    const ANCLAS = { "La Paz": [1, -8, "start"], "El Alto": [-1, 14, "end"] };
    const radio = (ton, mx) => 4 + 30 * Math.sqrt(ton / mx);

    const dibujarMapa = async () => {
      const c = await get("/api/mapa?anio=" + $("#anio").value);
      const mx = Math.max(1, ...c.map((d) => d.ton));
      $("#mapa").innerHTML = trazos.map((d) => `<path class="depto" fill-rule="evenodd" d="${d}"/>`).join("") +
        c.map((d) => {
          const r = radio(d.ton, mx), [lado, dy, ancla] = ANCLAS[d.ciudad] || [1, -8, "start"];
          const dx = lado > 0 ? r + 5 : -(r + 5);
          return `<g class="ciudad"><circle class="burbuja" cx="${X(d.lon).toFixed(1)}" cy="${Y(d.lat).toFixed(1)}" r="${r.toFixed(1)}"><title>${d.ciudad}: ${fmt(d.ton)} t</title></circle>` +
            `<text x="${(X(d.lon) + dx).toFixed(1)}" y="${(Y(d.lat) + dy).toFixed(1)}" text-anchor="${ancla}">${d.ciudad}</text></g>`;
        }).join("");
      $("#leyenda-mapa").innerHTML = [.25, .5, 1].map((f) =>
        `<span><svg width="72" height="72" viewBox="0 0 72 72" aria-hidden="true"><circle cx="36" cy="36" r="${radio(mx * f, mx).toFixed(1)}"/></svg>${fmt(mx * f)} t</span>`).join("");
    };
    $("#anio").addEventListener("change", dibujarMapa); dibujarMapa();
  },
  async tipos() {
    await llenarCiudades("ciudad", "La Paz");
    const run = async () => {
      const d = await get("/api/ciudad-tipo?ciudad=" + $("#ciudad").value), n = Object.keys(d.series);
      dibujar("evolucion", { type: "line", data: { labels: d.anios, datasets: n.map((k, i) => ({ label: k, data: d.series[k], borderColor: COLORES[i], pointRadius: 2 })) }, options: { scales: ejes } });
      const ult = d.anios.length - 1;
      dibujar("torta", { type: "doughnut", data: { labels: n, datasets: [{ data: n.map((k) => d.series[k][ult] || 0), backgroundColor: COLORES }] } });
    };
    $("#ciudad").addEventListener("change", run); run();
  },
  async analisis() {
    await llenarCiudades();
    const run = async () => {
      const c = $("#ciudad").value, a = await get("/api/anomalias?cat=" + c);
      $("#reporteLink").href = "/reporte/" + c;
      const flag = a.x.map((m) => a.anomalias.find((z) => z.mes == m));
      dibujar("descomp", { type: "line", data: { labels: a.x, datasets: [
        { label: "Real", data: a.y, borderColor: COLORES[0], pointRadius: 0 },
        { label: "Tendencia", data: a.tendencia, borderColor: COLORES[1], pointRadius: 0 },
        { label: "Atípico", data: a.y.map((v, i) => flag[i] ? v : null), borderColor: COLORES[2], backgroundColor: COLORES[2], pointRadius: 5, showLine: false }] }, options: { scales: ejes } });
      $("#anomalias").innerHTML = a.anomalias.length ? `<table class="hm"><tr><th>Mes</th><th>Toneladas</th><th>Desvíos</th></tr>${a.anomalias.map((z) => `<tr><th>${z.mes}</th><td>${fmt(z.ton)}</td><td>${z.z}</td></tr>`).join("")}</table>` : "<p class='nota'>Sin meses atípicos.</p>";
    };
    $("#ciudad").addEventListener("change", run); run();
    const k = await get("/api/correlacion");
    $("#corr").innerHTML = tabla(k.ciudades, k.ciudades.map((c, i) => [c, k.valores[i]]), (v) => v == null ? "<td></td>" : `<td style="background:rgba(15,92,110,${Math.max(0, v).toFixed(2)});color:${v > .5 ? "#fff" : "#14232b"}">${v}</td>`);
  },
  async simulador() {
    const c = await get("/api/composicion"), u = c.anios.length - 1, n = Object.keys(c.series);
    $("#sliders").innerHTML = n.map((k, i) => `<label>${k}<input type="range" min="0" max="50" value="0" data-i="${i}"><output>0 %</output></label>`).join("");
    const calc = () => {
      let ahorro = 0, base = 0;
      document.querySelectorAll("#sliders input").forEach((r) => { const t = c.series[n[r.dataset.i]][u] || 0; base += t; ahorro += t * r.value / 100; r.nextSibling.textContent = r.value + " %"; });
      $("#resultado").innerHTML = [[fmt(ahorro) + " t", `Ahorro al año (base ${c.anios[u]})`], [(100 * ahorro / base).toFixed(1) + " %", "Del total recolectado"], [fmt(ahorro / $("#camion").value), "Camiones menos al año"]]
        .map(([a, b]) => `<div class="kpi"><b>${a}</b><span>${b}</span></div>`).join("");
    };
    $("#sliders").addEventListener("input", calc); $("#camion").addEventListener("input", calc); calc();
  },
  async reporte() {
    const c = decodeURIComponent(document.body.dataset.ciudad);
    $("#titulo").textContent = "Reporte: " + c;
    const [[s], p] = await Promise.all([get(`/api/serie?cats=${c}&agg=anual`), get(`/api/pronostico?cat=${c}&meses=12`)]);
    const y = s.y.filter((_, i) => i < s.y.length - 1), ult = y.at(-1), prev = y.at(-2);
    $("#kpisC").innerHTML = [[fmt(ult) + " t", "Último año completo"], [((ult / prev - 1) * 100).toFixed(1) + " %", "Variación anual"], [fmt(Math.max(...y)) + " t", "Máximo histórico"]].map(([a, b]) => `<div class="kpi"><b>${a}</b><span>${b}</span></div>`).join("");
    dibujar("rSerie", { type: "bar", data: { labels: s.x, datasets: [{ label: c + " (t)", data: s.y, backgroundColor: COLORES[0] }] }, options: { scales: ejes } });
    if (c !== "Total") { const d = await get("/api/ciudad-tipo?ciudad=" + c), n = Object.keys(d.series);
      dibujar("rTipos", { type: "bar", data: { labels: d.anios, datasets: n.map((k, i) => ({ label: k, data: d.series[k], backgroundColor: COLORES[i] })) }, options: { scales: { x: { stacked: true }, y: { stacked: true } } } }); }
    dibujar("rPron", { type: "line", data: { labels: [...p.hist.x.slice(-24), ...p.pred.x], datasets: [{ label: "Histórico", data: [...p.hist.y.slice(-24), ...new Array(p.pred.x.length).fill(null)], borderColor: COLORES[0], pointRadius: 0 }, { label: "Pronóstico", data: [...new Array(24).fill(null), ...p.pred.y], borderColor: COLORES[1], borderDash: [6, 4], pointRadius: 0 }] } });
  },
});
paginas[document.body.dataset.page]?.();
