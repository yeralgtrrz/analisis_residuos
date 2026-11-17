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
    $("#hasta").innerHTML = opciones(meta.anios, meta.anio_ultimo_completo || meta.anios.at(-1));
    $("#anioRank").innerHTML = opciones(meta.anios_completos || meta.anios, k.anio);
    const serie = async () => {
      const [s] = await get(`/api/serie?cats=${$("#ciudad").value}&desde=${$("#desde").value}&hasta=${$("#hasta").value}&agg=${$("#agg").value}`);
      dibujar("serie", { type: "line", data: { labels: s.x, datasets: [{ label: s.nombre + " (t)", data: s.y, borderColor: COLORES[0], pointRadius: 0, tension: .2, spanGaps: true }] }, options: { scales: ejes } });
      $("#omitidos").textContent = s.omitidos?.length ? `Años omitidos por tener menos de 12 meses: ${s.omitidos.join(", ")}.` : "";
      $("#notaSerie").textContent = `Serie tratada sin interpolación; Sucre empieza en 2015 y Cobija se excluye de las vistas por ciudad.${s.recortado_desde ? ` Recorte aplicado desde ${s.recortado_desde}.` : ""}`;
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
      const orden = alinear(data);
      dibujar("comparar", { type: "line", data: { labels: orden.x, datasets: orden.series.map((s, i) => ({ label: s.nombre, data: s.y, borderColor: COLORES[i % 10], pointRadius: 0, spanGaps: true })) }, options: { scales: ejes } });
      $("#notaComparar").textContent = "Series tratadas sin interpolación. La suma de ciudades no iguala al Total porque Cobija se excluye de las vistas por ciudad: diferencia media 0,56 % y máxima 2,19 %.";
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
      const modelo = $("#modelo").value;
      const p = await get(`/api/pronostico?cat=${$("#ciudad").value}&meses=${$("#meses").value}&modelo=${encodeURIComponent(modelo)}`);
      $("#metodo").textContent = p.automatico
        ? (modelo === "auto" ? `Modelo elegido: ${p.metodo} (menor MAE)` : `Modelo no disponible; se usó ${p.metodo}`)
        : `Modelo forzado: ${p.metodo}`;
      $("#modelos").innerHTML = `<table class="hm"><tr><th>Modelo</th><th>MAE (t)</th><th>MAPE (%)</th></tr>` +
        p.modelos.map((m) => `<tr><th>${m.modelo}${m.modelo === p.metodo ? " ✓" : ""}</th><td>${fmt(m.mae)}</td><td>${m.mape ?? "—"}</td></tr>`).join("") +
        `</table><p class="nota">Backtesting con prueba desde ${p.corte} (${p.backtest.x.length} meses).</p>`;
      const h = p.hist;
      $("#notaPron").textContent = "Serie histórica tratada sin interpolación visual; el modelo interpola internamente para regularizar la serie mensual.";
      const pad = new Array(h.x.length).fill(null);
      dibujar("pronostico", { type: "line", data: { labels: [...h.x, ...p.pred.x], datasets: [
        { label: "Histórico", data: [...h.y, ...new Array(p.pred.x.length).fill(null)], borderColor: COLORES[0], pointRadius: 0, spanGaps: true },
        { label: "Pronóstico", data: [...pad, ...p.pred.y], borderColor: COLORES[1], borderDash: [6, 4], pointRadius: 0 },
        { label: "Mínimo", data: [...pad, ...p.pred.min], borderColor: "#e0a52666", pointRadius: 0, fill: "+1", backgroundColor: "#e0a52622" },
        { label: "Máximo", data: [...pad, ...p.pred.max], borderColor: "#e0a52666", pointRadius: 0 }] }, options: { scales: ejes } });

      const bt = p.backtest;
      const colores = { "Holt-Winters": COLORES[0], "SARIMA": COLORES[1], "Regresión lineal": COLORES[2] };
      const predicciones = Object.entries(bt.predicciones).map(([nombre, valores], i) => ({
        label: nombre, data: valores, borderColor: colores[nombre] || COLORES[(i + 3) % COLORES.length],
        borderWidth: nombre === p.metodo ? 2.5 : 1.5, borderDash: nombre === p.metodo ? [] : [5, 4],
        pointRadius: 2, tension: .2
      }));
      dibujar("backtest", { type: "line", data: { labels: bt.x, datasets: [
        { label: "Real", data: bt.real, borderColor: COLORES[8], borderWidth: 2.5, pointRadius: 2, tension: .2 },
        ...predicciones] }, options: { scales: ejes } });

      const nombres = p.modelos.map((m) => m.modelo);
      dibujar("metricas", { type: "bar", data: { labels: nombres, datasets: [
        { label: "MAE (t)", data: p.modelos.map((m) => m.mae), backgroundColor: COLORES[0], yAxisID: "y" },
        { label: "MAPE (%)", data: p.modelos.map((m) => m.mape), backgroundColor: COLORES[1], yAxisID: "y1" }] },
        options: { scales: { y: { position: "left", ticks: { callback: (v) => fmt(v) } },
          y1: { position: "right", grid: { drawOnChartArea: false } } } } });

      const res = p.residuos;
      dibujar("residuos", { type: "bar", data: { labels: res.x, datasets: [{
        label: `Residuos ${p.metodo} (t)`, data: res.y,
        backgroundColor: res.y.map((v) => v == null ? "transparent" : (v >= 0 ? COLORES[3] : COLORES[2])) }] },
        options: { scales: ejes } });
    };
    $("#ciudad").addEventListener("change", run); $("#meses").addEventListener("change", run);
    $("#modelo").addEventListener("change", run);
    run();
  },
  async calidad() {
    const meta = await get("/api/meta");
    $("#ciudadImp").innerHTML = opciones(meta.ciudades, "Sucre");
    const f = await get("/api/faltantes");
    const celda = (x) => `<td style="background:${x ? `rgba(180,69,47,${.2 + x / 12 * .8})` : "var(--mapa)"};color:${x > 6 ? "#fff" : "var(--tinta)"}">${x || ""}</td>`;
    $("#faltantes").innerHTML = `<table class="hm"><tr><th></th>${f.anios.map((a) => `<th>${a}</th>`).join("")}</tr>` + f.ciudades.map((c, i) => `<tr><th>${c}</th>${f.valores[i].map(celda).join("")}</tr>`).join("") + "</table>";

    const r = f.rachas.map((x) => `<tr><th>${x.ciudad}${x.excluida ? " (excluida)" : ""}</th>` +
      `<td>${x.excluida ? "—" : x.tratada}</td><td>${x.inicio_tratada && x.fin_tratada ? `${x.inicio_tratada} → ${x.fin_tratada}` : "—"}</td>` +
      `<td>${x.cruda}</td><td>${x.inicio_cruda && x.fin_cruda ? `${x.inicio_cruda} → ${x.fin_cruda}` : "—"}</td>` +
      `<td>${x.anios_afectados.length ? x.anios_afectados.join(", ") : "—"}</td></tr>`).join("");
    $("#rachas").innerHTML = `<table class="hm"><tr><th>Ciudad</th><th>Racha tratada</th><th>Período tratado</th><th>Racha cruda</th><th>Período crudo</th><th>Años con huecos</th></tr>${r}</table>`;

    const co = await get("/api/consistencia");
    $("#consistencia").innerHTML = `<table class="hm"><tr><th>Comparación</th><th>Período</th><th>Diferencia máxima</th></tr>` +
      `<tr><th>B vs C (B con Cobija)</th><td>${co.b_c.periodo}</td><td>${co.b_c.dif_max} % (${co.b_c.meses} meses)</td></tr>` +
      `<tr><th>B sin Cobija vs C</th><td>${co.b_sin_cobija_c.periodo}</td><td>media ${co.b_sin_cobija_c.dif_media} %, máximo ${co.b_sin_cobija_c.dif_max} % (${co.b_sin_cobija_c.meses} meses)</td></tr>` +
      `<tr><th>B vs A (ciudad-año)</th><td>${co.b_a.periodo}</td><td>${co.b_a.dif_max} % (${co.b_a.pares} pares)</td></tr></table>`;

    const lg = await get("/api/limpieza");
    $("#logLimpieza").innerHTML = `<table class="hm"><tr><th>Paso</th><th>Dataset</th><th>Problema</th><th>Cantidad</th><th>Método</th><th>Por qué</th></tr>` +
      lg.map((x) => `<tr><td>${x.paso}</td><td>${x.dataset}</td><td>${x.problema}</td><td>${x.cantidad}</td><td>${x.metodo}</td><td>${x.porque}</td></tr>`).join("") + "</table>";

    const dibujarCob = async () => {
      const ciudad = $("#ciudadImp").value;
      const s = await get("/api/cobertura?ciudad=" + ciudad);
      $("#detalleImp").textContent = `Huecos: ${s.n_huecos} meses · racha máxima: ${s.racha_max} meses` +
        `${s.inicio_racha ? ` (${s.inicio_racha} → ${s.fin_racha})` : ""} · recorte: ${s.recortado_desde || "sin recorte"}. Sin interpolación.`;
      dibujar("cobertura", { type: "line", data: { labels: s.x, datasets: [
        { label: ciudad + " (t)", data: s.y, borderColor: COLORES[0], pointRadius: 0, spanGaps: false }] }, options: { scales: ejes } });
    };
    $("#ciudadImp").addEventListener("change", dibujarCob);
    dibujarCob();
  },
};
const tabla = (cols, filas, color) => `<table class="hm"><tr><th></th>${cols.map((c) => `<th>${c}</th>`).join("")}</tr>` + filas.map(([n, v]) => `<tr><th>${n}</th>${v.map(color).join("")}</tr>`).join("") + "</table>";
const alinear = (datos) => {
  const x = [...new Set(datos.flatMap((d) => d.x))].sort();
  const series = datos.map((d) => {
    const m = new Map(d.x.map((v, j) => [v, d.y[j]]));
    return { nombre: d.nombre, y: x.map((v) => (m.has(v) ? m.get(v) : null)) };
  });
  return { x, series };
};
const llenarCiudades = async (id = "ciudad", def = "Total") => { const m = await get("/api/meta"); $("#" + id).innerHTML = opciones([def, ...m.ciudades]); return m; };

Object.assign(paginas, {
  async mapa() {
    const [m, geo] = await Promise.all([get("/api/meta"), get("/static/data/bolivia.json")]);
    $("#anio").innerHTML = opciones(m.anios_completos || m.anios, m.anio_ultimo_completo || 2025);

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
      const d = await get(`/api/ciudad-tipo?ciudad=${$("#ciudad").value}`), n = Object.keys(d.series);
      const base = n.map((k, i) => ({ label: k, data: d.series[k], borderColor: COLORES[i], pointRadius: 2, spanGaps: false }));
      dibujar("evolucion", { type: "line", data: { labels: d.anios, datasets: base }, options: { scales: ejes } });
      const ult = d.anios.length - 1;
      const partes = [];
      const nr = Object.values(d.no_reportado || {}).reduce((a, arr) => a + arr.filter(Boolean).length, 0);
      partes.push(`Serie tratada sin imputación: ${nr} celdas tipo-año sin dato se marcan como no reportadas y valen 0. Sucre empieza en 2015.`);
      if (d.totales?.[ult] != null) partes.push(`Total ${d.anios[ult]}: ${fmt(d.totales[ult])} t.`);
      $("#notaTipos").textContent = partes.join(" ");
      const vals = n.map((k) => [k, d.series[k][ult]]).filter(([, v]) => v != null);
      dibujar("torta", { type: "doughnut", data: { labels: vals.map(([k]) => k), datasets: [{ data: vals.map(([, v]) => v), backgroundColor: vals.map(([k]) => COLORES[n.indexOf(k) % COLORES.length]) }] } });
    };
    $("#ciudad").addEventListener("change", run); run();
  },
  async analisis() {
    await llenarCiudades();
    const run = async () => {
      const c = $("#ciudad").value, a = await get("/api/anomalias?cat=" + c);
      $("#reporteLink").href = "/reporte/" + c;
      const serie = a.y;
      $("#notaAnalisis").textContent = "Hampel local en log: mediana móvil de 13 meses y 4 MAD. La serie tratada no interpola; los valores atípicos se winsorizan con los límites locales.";
      const flag = a.out_local;
      dibujar("descomp", { type: "line", data: { labels: a.x, datasets: [
        { label: "Real", data: serie, borderColor: COLORES[0], pointRadius: 0, spanGaps: true },
        { label: "Mediana local", data: a.mediana_local, borderColor: COLORES[1], pointRadius: 0 },
        { label: "Atípico", data: serie.map((v, i) => flag[i] ? v : null), borderColor: COLORES[2], backgroundColor: COLORES[2], pointRadius: 5, showLine: false }] }, options: { scales: ejes } });
      $("#anomalias").innerHTML = a.anomalias.length ? `<table class="hm"><tr><th>Mes</th><th>Toneladas</th><th>Ton final</th><th>Mediana local</th><th>Desvío</th></tr>${a.anomalias.map((z) => `<tr><th>${z.mes}</th><td>${fmt(z.ton)}</td><td>${fmt(z.ton_final)}</td><td>${fmt(z.mediana)}</td><td>${z.desvio_pct} %</td></tr>`).join("")}</table>` : "<p class='nota'>Sin meses atípicos.</p>";
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
    $("#pdf").addEventListener("click", () => window.print());
    const [[s], p] = await Promise.all([get(`/api/serie?cats=${c}&agg=anual`), get(`/api/pronostico?cat=${c}&meses=12`)]);
    $("#pieReporte").textContent = "Fuente: datos tratados (Sucre desde 2015; sin interpolación; Cobija excluida de las vistas por ciudad). El Total nacional del INE incluye Cobija.";
    const ult = s.y.at(-1), prev = s.y.at(-2), imax = s.y.indexOf(Math.max(...s.y));
    $("#kpisC").innerHTML = [
      [fmt(ult) + " t", `Recolectado en ${s.x.at(-1)}`],
      [((ult / prev - 1) * 100).toFixed(1) + " %", `Variación vs ${s.x.at(-2)}`],
      [fmt(Math.max(...s.y)) + " t", `Máximo histórico (${s.x[imax]})`],
    ].map(([a, b]) => `<div class="kpi"><b>${a}</b><span>${b}</span></div>`).join("");
    dibujar("rSerie", { type: "bar", data: { labels: s.x, datasets: [{ label: c + " (t)", data: s.y, backgroundColor: COLORES[0] }] }, options: { scales: ejes } });
    if (c !== "Total") { const d = await get("/api/ciudad-tipo?ciudad=" + c), n = Object.keys(d.series);
      dibujar("rTipos", { type: "bar", data: { labels: d.anios, datasets: n.map((k, i) => ({ label: k, data: d.series[k], backgroundColor: COLORES[i] })) }, options: { scales: { x: { stacked: true }, y: { stacked: true } } } }); }
    dibujar("rPron", { type: "line", data: { labels: [...p.hist.x.slice(-24), ...p.pred.x], datasets: [{ label: "Histórico", data: [...p.hist.y.slice(-24), ...new Array(p.pred.x.length).fill(null)], borderColor: COLORES[0], pointRadius: 0 }, { label: "Pronóstico", data: [...new Array(Math.min(24, p.hist.y.length)).fill(null), ...p.pred.y], borderColor: COLORES[1], borderDash: [6, 4], pointRadius: 0 }] } });
  },
});

const tema = localStorage.getItem("tema") || (matchMedia("(prefers-color-scheme: dark)").matches ? "oscuro" : "claro");
document.documentElement.dataset.tema = tema;
document.querySelector("#tema")?.addEventListener("click", () => {
  localStorage.setItem("tema", document.documentElement.dataset.tema === "oscuro" ? "claro" : "oscuro");
  location.reload();
});
try {
  const cs = getComputedStyle(document.documentElement);
  Chart.defaults.color = cs.getPropertyValue("--tinta").trim();
  Chart.defaults.borderColor = cs.getPropertyValue("--borde").trim();
} catch (e) { /* Chart aún no cargado */ }

paginas[document.body.dataset.page]?.();
