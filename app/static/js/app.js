const $ = (s) => document.querySelector(s);
const fmt = (n) => Math.round(n).toLocaleString("es-BO");
const COLORES = ["#168577", "#c78318", "#c54c69", "#5b8c42", "#7855bf", "#2687c5", "#aa6336", "#b84e9e", "#526485", "#458eaa"];
const get = (url) => fetch(url).then((r) => r.json());
const charts = {};
function dibujar(id, config) {
  charts[id]?.destroy();
  charts[id] = new Chart($("#" + id), config);
}
const opciones = (arr, sel) => arr.map((v) => `<option ${v == sel ? "selected" : ""}>${v}</option>`).join("");
const cabeceraTabla = (titulos, numericas = []) => `<thead><tr>${titulos.map((titulo, i) =>
  `<th scope="col"${numericas.includes(i) ? ' class="numero"' : ""}>${titulo}</th>`
).join("")}</tr></thead>`;
const tablaCalor = (encabezados, filas, celda) => `<table class="tabla-datos tabla-calor">${cabeceraTabla(encabezados)}<tbody>` +
  filas.map(([nombre, valores]) => `<tr><th scope="row">${nombre}</th>${valores.map(celda).join("")}</tr>`).join("") + "</tbody></table>";
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
    $("#anioRank").innerHTML = opciones(meta.anios_completos || meta.anios, k.anio);
    const rank = async () => {
      const r = await get("/api/ranking?anio=" + $("#anioRank").value);
      dibujar("ranking", { type: "bar", data: { labels: r.labels, datasets: [{ label: "Toneladas", data: r.values, backgroundColor: COLORES[0] }] }, options: { indexAxis: "y", plugins: { legend: { display: false } } } });
    };
    $("#anioRank").addEventListener("change", rank);
    const c = await get("/api/composicion");
    dibujar("composicion", { type: "bar", data: { labels: c.anios, datasets: Object.entries(c.series).map(([n, y], i) => ({ label: n, data: y, backgroundColor: COLORES[i] })) }, options: { scales: { x: { stacked: true }, y: { stacked: true, ticks: { callback: fmt } } } } });
    await rank();
  },
  async comparar() {
    const meta = await get("/api/meta");
    $("#chips").innerHTML = meta.ciudades.map((c, i) => `<label><input type="checkbox" value="${c}" ${i < 3 ? "checked" : ""}>${c}</label>`).join("");
    const comparar = async () => {
      const cats = [...document.querySelectorAll("#chips input:checked")].map((i) => i.value);
      if (!cats.length) return;
      const data = await get(`/api/serie?cats=${cats.join(",")}&agg=${$("#agg").value}`);
      const orden = alinear(data);
      dibujar("comparar", { type: "line", data: { labels: orden.x, datasets: orden.series.map((s, i) => ({ label: s.nombre, data: s.y, borderColor: COLORES[i % 10], pointRadius: 0, spanGaps: false })) }, options: { scales: ejes } });
      $("#notaComparar").textContent = "Selecciona las ciudades que quieres comparar. Los cortes en las series mensuales indican meses sin dato.";
    };
    $("#chips").addEventListener("change", comparar); $("#agg").addEventListener("change", comparar);
    $("#hmCiudad").innerHTML = opciones(["Total", ...meta.ciudades]);
    const hm = async () => {
      const h = await get("/api/heatmap?cat=" + $("#hmCiudad").value);
      const v = h.valores.flat().filter((x) => x != null), mn = Math.min(...v), mx = Math.max(...v);
      const celda = (x) => x == null ? "<td></td>" : `<td style="background:rgba(15,92,110,${(.1 + .8 * (x - mn) / (mx - mn)).toFixed(2)});color:${(x - mn) / (mx - mn) > .55 ? "#fff" : "#14232b"}">${fmt(x)}</td>`;
      $("#heatmap").innerHTML = tablaCalor(["Año", ...h.meses], h.anios.map((a, i) => [a, h.valores[i]]), celda);
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
      if (p.error) { $("#metodo").textContent = p.error; return; }
      $("#metodo").textContent = p.automatico
        ? (modelo === "auto" ? `Modelo elegido: ${p.metodo} (menor MAE)` : `Modelo no disponible; se usó ${p.metodo}`)
        : `Modelo forzado: ${p.metodo}`;
      $("#modelos").innerHTML = `<div class="scroll marco-tabla"><table class="tabla-datos">${cabeceraTabla(["Modelo", "MAE (t)", "MAPE (%)"], [1, 2])}<tbody>` +
        p.modelos.map((m) => `<tr><th scope="row">${m.modelo}${m.modelo === p.metodo ? " ✓" : ""}</th><td class="numero">${fmt(m.mae)}</td><td class="numero">${m.mape ?? "—"}</td></tr>`).join("") +
        `</tbody></table></div><p class="nota">Backtesting con prueba desde ${p.corte} (${p.backtest.x.length} meses).</p>`;
      const h = p.hist;
      $("#notaPron").textContent = "Serie histórica tratada sin interpolación visual; el modelo interpola internamente para regularizar la serie mensual.";
      const pad = new Array(h.x.length).fill(null);
      dibujar("pronostico", { type: "line", data: { labels: [...h.x, ...p.pred.x], datasets: [
        { label: "Histórico", data: [...h.y, ...new Array(p.pred.x.length).fill(null)], borderColor: COLORES[0], pointRadius: 0, spanGaps: false },
        { label: "Pronóstico", data: [...pad, ...p.pred.y], borderColor: COLORES[1], borderDash: [6, 4], pointRadius: 0 },
        { label: "Mínimo", data: [...pad, ...p.pred.min], borderColor: "#e0a52666", pointRadius: 0, fill: "+1", backgroundColor: "#e0a52622" },
        { label: "Máximo", data: [...pad, ...p.pred.max], borderColor: "#e0a52666", pointRadius: 0 }] }, options: { scales: ejes } });

      const bt = p.backtest;
      const colores = { "Holt-Winters": COLORES[0], "SARIMA": COLORES[1], "Regresión lineal": COLORES[2], "Modelo predictivo": COLORES[3] };
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

    const r = f.rachas.map((x) => `<tr><th scope="row">${x.ciudad}${x.excluida ? " (excluida)" : ""}</th>` +
      `<td class="numero">${x.excluida ? "—" : x.tratada}</td><td>${x.inicio_tratada && x.fin_tratada ? `${x.inicio_tratada} → ${x.fin_tratada}` : "—"}</td>` +
      `<td class="numero">${x.cruda}</td><td>${x.inicio_cruda && x.fin_cruda ? `${x.inicio_cruda} → ${x.fin_cruda}` : "—"}</td>` +
      `<td>${x.anios_afectados.length ? x.anios_afectados.join(", ") : "—"}</td></tr>`).join("");
    $("#rachas").innerHTML = `<table class="tabla-datos">${cabeceraTabla([
      "Ciudad", "Racha tratada", "Período tratado", "Racha cruda", "Período crudo", "Años con huecos",
    ], [1, 3])}<tbody>${r}</tbody></table>`;

    const co = await get("/api/consistencia");
    $("#consistencia").innerHTML = `<table class="tabla-datos">${cabeceraTabla(["Comparación", "Período", "Diferencia máxima"], [2])}<tbody>` +
      `<tr><th scope="row">B vs C (B con Cobija)</th><td>${co.b_c.periodo}</td><td class="numero">${co.b_c.dif_max} % (${co.b_c.meses} meses)</td></tr>` +
      `<tr><th scope="row">B sin Cobija vs C</th><td>${co.b_sin_cobija_c.periodo}</td><td class="numero">media ${co.b_sin_cobija_c.dif_media} %, máximo ${co.b_sin_cobija_c.dif_max} % (${co.b_sin_cobija_c.meses} meses)</td></tr>` +
      `<tr><th scope="row">B vs A (ciudad-año)</th><td>${co.b_a.periodo}</td><td class="numero">${co.b_a.dif_max} % (${co.b_a.pares} pares)</td></tr></tbody></table>`;

    const lg = await get("/api/limpieza");
    $("#logLimpieza").innerHTML = `<table class="tabla-datos">${cabeceraTabla(["Paso", "Dataset", "Problema", "Cantidad", "Método", "Por qué"], [3])}<tbody>` +
      lg.map((x) => `<tr><th scope="row">${x.paso}</th><td>${x.dataset}</td><td>${x.problema}</td><td${typeof x.cantidad === "number" ? ' class="numero"' : ""}>${x.cantidad}</td><td>${x.metodo}</td><td>${x.porque}</td></tr>`).join("") + "</tbody></table>";

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
  async prediccion() {
    const meta = await get("/api/meta");
    const ciudad = $("#ciudad"), horizonte = $("#meses");
    const anioTabla = $("#anioTablaPred"), tabla = $("#tablaPred");
    ciudad.innerHTML = opciones(meta.ciudades, "La Paz");
    let datos, solicitud = 0;

    const mostrarProyeccion = () => {
      if (!datos) return;
      const meses = Number(horizonte.value);
      const p = datos;
      const pred = Object.fromEntries(Object.entries(p.pred).map(([campo, serie]) => [campo, serie.slice(0, meses)]));
      const total = pred.y.reduce((suma, valor) => suma + valor, 0);
      $("#kpisPred").innerHTML = [
        [fmt(pred.y[0]) + " t", `Primer mes (${pred.x[0]})`],
        [fmt(total / meses) + " t", "Promedio mensual proyectado"],
        [fmt(total) + " t", `Total en ${meses} meses`],
        [fmt(p.mae) + " t", "Error típico (MAE de prueba)"],
      ].map(([a, b]) => `<div class="kpi"><b>${a}</b><span>${b}</span></div>`).join("");
      const h = p.historico, pad = new Array(h.x.length).fill(null);
      dibujar("prediccion", { type: "line", data: { labels: [...h.x, ...pred.x], datasets: [
        { label: "Histórico", data: [...h.y, ...new Array(pred.x.length).fill(null)], borderColor: COLORES[0], pointRadius: 0, spanGaps: false },
        { label: "Predicción", data: [...pad, ...pred.y], borderColor: COLORES[1], borderDash: [6, 4], pointRadius: 2 },
        { label: "Mínimo", data: [...pad, ...pred.min], borderColor: "#e0a52666", pointRadius: 0, fill: "+1", backgroundColor: "#e0a52622" },
        { label: "Máximo", data: [...pad, ...pred.max], borderColor: "#e0a52666", pointRadius: 0 },
      ] }, options: { scales: ejes } });
    };

    const mostrarTabla = () => {
      const { historico, pred } = datos;
      const observados = new Map(historico.x.map((fecha, i) => [fecha, historico.y[i]]));
      const proyectados = new Map(pred.x.map((fecha, i) => [fecha, i]));
      const filas = Array.from({ length: 12 }, (_, mes) => {
        const fecha = `${anioTabla.value}-${String(mes + 1).padStart(2, "0")}`;
        const i = proyectados.get(fecha);
        const real = observados.get(fecha);
        const origen = i != null ? "Proyección" : real != null ? "Real" : "Sin dato";
        const toneladas = i != null ? fmt(pred.y[i]) : real != null ? fmt(real) : "—";
        const minimo = i != null ? fmt(pred.min[i]) : "—";
        const maximo = i != null ? fmt(pred.max[i]) : "—";
        return `<tr>
          <th scope="row"><span class="prediccion-mes">
            <time datetime="${fecha}">${fecha}</time>
            <span class="prediccion-origen"${origen === "Real" ? ' data-origen="real"' : ""}>${origen}</span>
          </span></th>
          <td class="prediccion-toneladas">${toneladas}</td><td>${minimo}</td><td>${maximo}</td>
        </tr>`;
      }).join("");
      tabla.innerHTML = `<table class="prediccion-tabla" aria-labelledby="tituloTablaPred">
        ${cabeceraTabla(["Mes", "Toneladas", "Mínimo", "Máximo"])}<tbody>${filas}</tbody></table>`;
    };

    const cargarCiudad = async () => {
      const numero = ++solicitud;
      datos = null;
      anioTabla.disabled = true;
      tabla.setAttribute("aria-busy", "true");
      tabla.textContent = "Cargando meses…";
      const p = await get(`/api/predecir?ciudad=${encodeURIComponent(ciudad.value)}&meses=24`)
        .catch(() => ({ error: "No se pudo cargar la predicción." }));
      if (numero !== solicitud) return;
      tabla.setAttribute("aria-busy", "false");
      const alerta = $("#alertaPred");
      if (p.error) {
        alerta.className = "aviso error";
        alerta.textContent = p.error;
        $("#kpisPred").innerHTML = "";
        $("#notaPred").textContent = "";
        charts.prediccion?.destroy();
        delete charts.prediccion;
        tabla.textContent = "La tabla está disponible para ciudades con predicción.";
        return;
      }
      datos = p;
      if (p.alerta) {
        const a = p.alerta;
        alerta.className = "alerta-pico " + a.nivel;
        alerta.textContent = a.nivel === "bajo"
          ? `Probabilidad de pico para ${a.fecha} en ${p.ciudad}: ${a.probabilidad} %. Nivel bajo.`
          : `Alerta ${a.nivel} de pico en ${p.ciudad}: ${a.probabilidad} % de probabilidad para el mes siguiente.`;
      } else {
        alerta.className = "oculto";
      }
      $("#notaPred").textContent = `Último dato real: ${p.fecha_ultima}. Modelo de 5 variables; MAE de prueba ${fmt(p.mae)} t, RMSE ${fmt(p.rmse)} t, R² ${p.r2}. La serie tratada no se interpola para mostrar.`;

      const ultimoAnio = Number(p.fecha_ultima.slice(0, 4));
      const anios = [ultimoAnio, ultimoAnio + 1];
      const anterior = Number(anioTabla.value);
      anioTabla.innerHTML = opciones(anios, anios.includes(anterior) ? anterior : ultimoAnio);
      mostrarTabla();
      anioTabla.disabled = false;
      mostrarProyeccion();
    };
    ciudad.addEventListener("change", cargarCiudad);
    horizonte.addEventListener("change", mostrarProyeccion);
    anioTabla.addEventListener("change", mostrarTabla);
    await cargarCiudad();
  },
  async modelos() {
    const m = await get("/api/modelos");
    if (m.error) { $("#notaModelo").textContent = m.error; return; }
    const k = m.metricas;
    $("#nombreModelo").textContent = m.modelo;
    $("#kpisModelo").innerHTML = [
      [fmt(k.mae) + " t", "MAE de prueba"],
      [fmt(k.rmse) + " t", "RMSE de prueba"],
      [k.r2.toFixed(3), "R² de prueba"],
      [fmt(m.entrenamiento.filas), "Filas de entrenamiento"],
    ].map(([a, b]) => `<div class="kpi"><b>${a}</b><span>${b}</span></div>`).join("");
    $("#notaModelo").textContent = `Prueba desde ${m.prueba.desde} · ${fmt(m.prueba.filas)} registros de prueba · Datos hasta ${m.entrenamiento.hasta}`;
    $("#tablaModelos").innerHTML = `<table class="tabla-datos">${cabeceraTabla(["Modelo", "Objetivo", "MAE", "RMSE", "R²"], [2, 3, 4])}<tbody>` +
      m.modelos.map((x) => `<tr><th scope="row">${x.nombre}</th><td>${x.objetivo}</td><td class="numero">${fmt(x.mae)}</td><td class="numero">${fmt(x.rmse)}</td><td class="numero">${x.r2.toFixed(3)}</td></tr>`).join("") + "</tbody></table>";
    dibujar("maeModelos", { type: "bar", data: { labels: m.modelos.map((x) => x.nombre), datasets: [
      { label: "MAE (t)", data: m.modelos.map((x) => x.mae), backgroundColor: m.modelos.map((x) => x.nombre === m.modelo ? COLORES[1] : COLORES[0]) }] },
      options: { indexAxis: "y", plugins: { legend: { display: false } }, scales: { x: { ticks: { callback: (v) => fmt(v) } } } } });
    const imp = [...m.importancia].sort((a, b) => a.valor - b.valor);
    dibujar("importancia", { type: "bar", data: { labels: imp.map((x) => x.variable), datasets: [
      { label: "Importancia", data: imp.map((x) => x.valor), backgroundColor: COLORES[3] }] },
      options: { indexAxis: "y", plugins: { legend: { display: false } } } });
    $("#coeficientes").innerHTML = `<table class="tabla-datos">${cabeceraTabla(["Variable", "Coeficiente"], [1])}<tbody>` +
      m.coeficientes.map((x) => `<tr><th scope="row">${x.variable}</th><td class="numero">${x.coeficiente.toFixed(3)}</td></tr>`).join("") +
      `<tr><th scope="row">Intercepto</th><td class="numero">${m.intercepto.toFixed(3)}</td></tr></tbody></table>`;
    const ficha = [
      ["Modelo", m.modelo], ["Variables", m.features.join(", ")], ["Objetivo", m.objetivo],
      ["Corte", m.corte], ["Entrenamiento", `${m.entrenamiento.desde} a ${m.entrenamiento.hasta}`],
      ["Filas de entrenamiento", fmt(m.entrenamiento.filas), true], ["Prueba", `${m.prueba.desde} (${fmt(m.prueba.filas)} filas)`],
      ["Actualización", m.actualizado.slice(0, 10)],
      ["MAE", `${fmt(k.mae)} t`, true], ["RMSE", `${fmt(k.rmse)} t`, true], ["R²", k.r2, true],
    ];
    $("#fichaModelo").innerHTML = `<table class="tabla-datos">${cabeceraTabla(["Campo", "Valor"])}<tbody>` +
      ficha.map(([campo, valor, numerico]) =>
        `<tr><th scope="row">${campo}</th><td${numerico ? ' class="numero"' : ""}>${valor}</td></tr>`).join("") + "</tbody></table>";
  },
  async perfiles() {
    const estado = $("#estadoDetallePerfil");
    const p = await get("/api/perfiles").catch(() => ({ error: "No se pudieron cargar los perfiles." }));
    if (p.error) {
      estado.textContent = p.error;
      return;
    }
    const clase = (nombre) => nombre === "En expansión" ? "perfil-expansion" : (nombre === "Volumen alto estable" ? "perfil-alto" : "perfil-bajo");
    $("#gruposPerfil").innerHTML = p.grupos.map((g) =>
      `<div class="kpi ${clase(g.nombre)}"><b>${g.nombre}</b><span>${fmt(g.toneladas_medias)} t de media · CV ${g.cv} · crecimiento ${(g.crecimiento * 100).toFixed(1)} %</span></div>`).join("");
    if (typeof Chart !== "undefined") dibujar("planoPerfiles", {
      type: "scatter",
      data: { datasets: p.grupos.map((g, i) => ({
        label: g.nombre,
        data: p.filas.filter((fila) => fila.perfil === g.nombre).map((fila) => ({
          x: fila.toneladas, y: fila.cv * 100, ciudad: fila.ciudad, anio: fila.anio,
        })),
        backgroundColor: COLORES[i],
        pointRadius: ({ raw }) => raw?.ciudad === "Cobija" ? 6 : 4,
        pointBorderWidth: ({ raw }) => raw?.ciudad === "Cobija" ? 2 : 0,
        pointBorderColor: getComputedStyle(document.documentElement).getPropertyValue("--tinta").trim(),
      })) },
      options: {
        scales: {
          x: { title: { display: true, text: "Promedio mensual (t)" }, ticks: { callback: fmt } },
          y: { title: { display: true, text: "Coeficiente de variación (%)" }, beginAtZero: true },
        },
        plugins: { tooltip: { callbacks: { label: ({ raw }) =>
          raw.ciudad + " · " + raw.anio + " · " + fmt(raw.x) + " t · CV " + raw.y.toFixed(1) + "%"
        } } },
      },
    });
    const por = new Map(p.filas.map((x) => [x.ciudad + "|" + x.anio, x]));
    $("#matrizPerfiles").innerHTML = `<table class="tabla-datos tabla-calor perfiles">${cabeceraTabla(["Ciudad", ...p.anios])}<tbody>` +
      p.ciudades.map((c) => `<tr><th scope="row">${c}</th>${p.anios.map((a) => {
        const x = por.get(c + "|" + a);
        if (!x) return "<td></td>";
        return `<td class="${clase(x.perfil)}" title="${c} ${a}: ${fmt(x.toneladas)} t, CV ${x.cv}, crecimiento ${(x.crecimiento * 100).toFixed(1)} %">${x.perfil === "En expansión" ? "E" : (x.perfil === "Volumen alto estable" ? "A" : "B")}</td>`;
      }).join("")}</tr>`).join("") + "</tbody></table>";
    if (!p.filas.length) {
      estado.textContent = "No hay años con perfiles disponibles.";
      return;
    }
    const ciudad = $("#ciudadPerfil"), anio = $("#anioPerfil"), ficha = $("#fichaPerfil");
    const grupos = {
      "En expansión": "El grupo se caracteriza por un mayor crecimiento del promedio mensual de recolección.",
      "Volumen alto estable": "El grupo reúne registros con un promedio mensual alto y un crecimiento moderado según su perfil.",
      "Volumen bajo estable": "El grupo reúne registros con un promedio mensual bajo y un crecimiento moderado según su perfil.",
    };
    const porcentaje = new Intl.NumberFormat("es-BO", { style: "percent", maximumFractionDigits: 1 });
    const cambio = new Intl.NumberFormat("es-BO", { style: "percent", maximumFractionDigits: 1, signDisplay: "exceptZero" });
    const mostrarFicha = () => {
      const fila = por.get(ciudad.value + "|" + anio.value);
      $("#periodoPerfil").textContent = fila.ciudad + " · " + fila.anio;
      $("#grupoDetallePerfil").textContent = fila.perfil;
      $("#descripcionPerfil").textContent = grupos[fila.perfil];
      $("#mediaPerfil").textContent = fmt(fila.toneladas) + " t";
      $("#variabilidadPerfil").textContent = porcentaje.format(fila.cv);
      $("#crecimientoPerfil").textContent = cambio.format(fila.crecimiento);
      ficha.dataset.grupo = clase(fila.perfil);
      ficha.hidden = false;
    };
    const actualizarAnios = () => {
      const anterior = Number(anio.value);
      const anios = p.anios.filter((a) => por.has(ciudad.value + "|" + a)).reverse();
      anio.innerHTML = opciones(anios, anios.includes(anterior) ? anterior : anios[0]);
      mostrarFicha();
    };
    ciudad.innerHTML = opciones(p.ciudades);
    ciudad.disabled = anio.disabled = false;
    ciudad.addEventListener("change", actualizarAnios);
    anio.addEventListener("change", mostrarFicha);
    actualizarAnios();
    estado.hidden = true;
  },
};
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
    const mapa = $("#mapa"), estado = $("#estadoMapa"), leyenda = $("#leyenda-mapa");
    const selectorAnio = $("#anio"), modo = $("#compararMapa");
    const detalle = $("#detalleMapa"), selectorCiudad = $("#ciudadMapa");
    let datos, solicitud = 0;

    const cargarMediciones = async () => {
      const [meta, geo] = await Promise.all([get("/api/meta"), get("/static/data/bolivia.json")]);
      const categorias = encodeURIComponent(["Total", ...meta.ciudades].join(","));
      const series = await get("/api/serie?agg=anual&cats=" + categorias);
      const mediciones = new Map(series.map((s) => [s.nombre,
        new Map(s.x.map((anio, i) => [Number(anio), s.y[i]])),
      ]));
      return { meta, geo, mediciones };
    };
    const fuentes = await cargarMediciones().catch(() => null);
    if (!fuentes) {
      estado.textContent = "No se pudieron cargar los datos del mapa.";
      return;
    }
    const { meta, geo, mediciones } = fuentes;
    selectorAnio.innerHTML = opciones(meta.anios_completos, meta.anio_ultimo_completo);
    selectorAnio.disabled = false;

    const W = 520, H = 560, pad = 18;
    const [minLon, minLat, maxLon, maxLat] = geo.bbox;
    const esc = Math.min((W - 2 * pad) / (maxLon - minLon), (H - 2 * pad) / (maxLat - minLat));
    const offX = pad + (W - 2 * pad - (maxLon - minLon) * esc) / 2;
    const offY = pad + (H - 2 * pad - (maxLat - minLat) * esc) / 2;
    const X = (lon) => offX + (lon - minLon) * esc;
    const Y = (lat) => offY + (maxLat - lat) * esc;

    const trazos = geo.departamentos.map((d) => {
      const trazo = d.anillos.map((a) =>
        "M" + a.map(([lon, lat]) => X(lon).toFixed(1) + "," + Y(lat).toFixed(1)).join("L") + "Z").join("");
      return `<path class="depto" fill-rule="evenodd" d="${trazo}"/>`;
    }).join("");
    const ANCLAS = { "La Paz": [1, -8, "start"], "El Alto": [-1, 14, "end"] };
    const radio = (ton, maximo) => 4 + 30 * Math.sqrt(ton / Math.max(maximo, 1));
    const rutaReporte = (ciudad) => "/reporte/" + encodeURIComponent(ciudad);
    const porcentaje = new Intl.NumberFormat("es-BO", { style: "percent", maximumFractionDigits: 2 });
    const porcentajeCambio = new Intl.NumberFormat("es-BO", {
      style: "percent", maximumFractionDigits: 2, signDisplay: "exceptZero",
    });
    const medido = (ciudad, anio) => mediciones.get(ciudad)?.get(anio);
    const variacion = (ciudad, anio) => {
      const actual = medido(ciudad, anio), anterior = medido(ciudad, anio - 1);
      return actual != null && anterior > 0 ? actual / anterior - 1 : null;
    };
    const estados = {
      sube: "Aumentó", baja: "Disminuyó", igual: "Sin cambio", incompleto: "Sin datos comparables",
    };
    const tendencia = (valor) => {
      if (valor == null) return "incompleto";
      if (valor > 0) return "sube";
      return valor < 0 ? "baja" : "igual";
    };

    const mostrarDetalle = () => {
      const { anio, ciudades, puestos } = datos;
      const { ciudad, ton } = ciudades.find((d) => d.ciudad === selectorCiudad.value);
      const total = medido("Total", anio);
      const cambio = variacion(ciudad, anio);
      $("#periodoMapa").textContent = `${ciudad} · ${anio}`;
      $("#toneladasMapa").textContent = `${fmt(ton)} t`;
      $("#participacionMapa").textContent = total > 0 ? porcentaje.format(ton / total) : "Sin dato";
      $("#puestoMapa").textContent = `${puestos.get(ciudad)} de ${puestos.size}`;
      $("#tituloVariacionMapa").textContent = `Cambio frente a ${anio - 1}`;
      $("#variacionMapa").textContent = cambio == null ? "Sin datos comparables" : porcentajeCambio.format(cambio);
      $("#variacionMapa").dataset.tendencia = tendencia(cambio);
      const notas = [];
      if (medido(ciudad, anio) == null) {
        notas.push("El volumen, la participación y el puesto se calculan con los meses registrados de la ciudad.");
      }
      if (cambio == null) {
        notas.push("Para calcular la variación se requieren 12 meses con datos en ambos años y un valor anterior mayor que cero.");
      }
      const nota = $("#notaDetalleMapa");
      nota.textContent = notas.join(" ");
      nota.hidden = !notas.length;
      $("#reporteMapa").href = rutaReporte(ciudad);

      for (const enlace of mapa.querySelectorAll("a[data-ciudad]")) {
        enlace.toggleAttribute("data-seleccionada", enlace.dataset.ciudad === ciudad);
      }
    };

    const dibujarMapa = () => {
      const { anio, ciudades } = datos;
      const volumenes = ciudades.map((d) => d.ton);
      const minimo = Math.min(...volumenes), maximo = Math.max(...volumenes);
      mapa.innerHTML = trazos + ciudades.map((d) => {
        const r = radio(d.ton, maximo);
        const [lado, dy, ancla] = ANCLAS[d.ciudad] || [1, -8, "start"];
        const dx = lado * (r + 5);
        const cambio = variacion(d.ciudad, anio);
        const clase = tendencia(cambio);
        const textoCambio = cambio == null ? estados[clase] : `${estados[clase]} ${porcentaje.format(Math.abs(cambio))}`;
        const rotulo = `${d.ciudad}, ${fmt(d.ton)} toneladas en ${anio}${modo.checked ? ". " + textoCambio : ""}`;
        return `<a class="ciudad${modo.checked ? " " + clase : ""}" href="${rutaReporte(d.ciudad)}" tabindex="0" data-ciudad="${d.ciudad}" aria-label="Abrir reporte de ${rotulo}">
          <title>${rotulo}</title>
          <circle class="burbuja" cx="${X(d.lon).toFixed(1)}" cy="${Y(d.lat).toFixed(1)}" r="${r.toFixed(1)}"/>
          <text x="${(X(d.lon) + dx).toFixed(1)}" y="${(Y(d.lat) + dy).toFixed(1)}" text-anchor="${ancla}">${d.ciudad}</text>
        </a>`;
      }).join("");

      const muestra = (etiqueta, ton) => `<span><svg width="72" height="72" viewBox="0 0 72 72" aria-hidden="true"><circle cx="36" cy="36" r="${radio(ton, maximo).toFixed(1)}"/></svg>${etiqueta} ${fmt(ton)} t</span>`;
      leyenda.innerHTML = `<p class="mapa-leyenda-titulo">Toneladas registradas en ${anio}</p>
        <div class="leyenda">${muestra("Mínimo", minimo)}${muestra("Máximo", maximo)}</div>`;
      if (modo.checked) {
        leyenda.innerHTML += `<p class="mapa-leyenda-titulo">Cambio frente a ${anio - 1}</p><div class="leyenda leyenda-tendencia">${Object.entries(estados)
          .map(([clase, texto]) => `<span><i class="${clase}" aria-hidden="true"></i>${texto}</span>`).join("")}</div>`;
      }
      mostrarDetalle();
    };

    const cargarAnio = async () => {
      const anio = Number(selectorAnio.value);
      const numero = ++solicitud;
      estado.textContent = `Cargando datos de ${anio}…`;
      estado.hidden = false;
      detalle.hidden = true;
      modo.disabled = true;
      mapa.innerHTML = trazos;
      leyenda.innerHTML = "";
      const resultado = await Promise.all([
        get("/api/mapa?anio=" + anio),
        get("/api/ranking?anio=" + anio),
      ]).catch(() => null);
      if (numero !== solicitud) return;
      if (!resultado) {
        estado.textContent = `No se pudieron cargar los datos de ${anio}.`;
        return;
      }
      const [ciudades, ranking] = resultado;
      if (!ciudades.length) {
        estado.textContent = `No hay ciudades con datos para ${anio}.`;
        return;
      }
      const puestos = new Map();
      ranking.labels.forEach((ciudad, i) => {
        if (ranking.values[i] != null) puestos.set(ciudad, puestos.size + 1);
      });
      const nombres = ciudades.map((d) => d.ciudad).sort((a, b) => a.localeCompare(b, "es-BO"));
      const elegida = nombres.includes(selectorCiudad.value) ? selectorCiudad.value : ciudades[0].ciudad;
      selectorCiudad.innerHTML = opciones(nombres, elegida);
      datos = { anio, ciudades, puestos };
      dibujarMapa();
      estado.hidden = true;
      detalle.hidden = false;
      modo.disabled = false;
    };

    selectorAnio.addEventListener("change", cargarAnio);
    modo.addEventListener("change", dibujarMapa);
    selectorCiudad.addEventListener("change", mostrarDetalle);
    mapa.addEventListener("focusin", (event) => {
      const ciudad = event.target.closest("a[data-ciudad]")?.dataset.ciudad;
      if (ciudad) {
        selectorCiudad.value = ciudad;
        mostrarDetalle();
      }
    });
    await cargarAnio();
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
      if (nr) partes.push(`${nr} celdas de procedencia sin dato.`);
      if (d.anios_incompletos.length) partes.push(`Años sin registro: ${d.anios_incompletos.join(", ")}.`);
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
        { label: "Real", data: serie, borderColor: COLORES[0], pointRadius: 0, spanGaps: false },
        { label: "Mediana local", data: a.mediana_local, borderColor: COLORES[1], pointRadius: 0 },
        { label: "Atípico", data: serie.map((v, i) => flag[i] ? v : null), borderColor: COLORES[2], backgroundColor: COLORES[2], pointRadius: 5, showLine: false }] }, options: { maintainAspectRatio: false, scales: ejes } });
      $("#anomalias").innerHTML = a.anomalias.length
        ? `<table class="tabla-datos">${cabeceraTabla(["Mes", "Toneladas", "Ton final", "Mediana local", "Desvío"], [1, 2, 3, 4])}<tbody>` +
          a.anomalias.map((z) => `<tr><th scope="row">${z.mes}</th><td class="numero">${fmt(z.ton)}</td><td class="numero">${fmt(z.ton_final)}</td><td class="numero">${fmt(z.mediana)}</td><td class="numero">${z.desvio_pct} %</td></tr>`).join("") +
          "</tbody></table>"
        : "<p class='nota'>Sin meses atípicos.</p>";
    };
    $("#ciudad").addEventListener("change", run); run();
    const k = await get("/api/correlacion");
    $("#corr").innerHTML = tablaCalor(["Ciudad", ...k.ciudades], k.ciudades.map((c, i) => [c, k.valores[i]]), (v) => v == null ? "<td></td>" : `<td style="background:rgba(15,92,110,${Math.max(0, v).toFixed(2)});color:${v > .5 ? "#fff" : "#14232b"}">${v}</td>`);
  },
  async simulador() {
    const datos = await get("/api/composicion").catch(() => null);
    const i = (datos?.anios?.length ?? 0) - 1;
    const baseSimulador = $("#baseSimulador");
    if (i < 0) {
      baseSimulador.textContent = "No se pudo cargar la composición del último año completo.";
      return;
    }
    const anio = datos.anios[i];
    const claves = { Domiciliarios: "dom", Mercados: "merc", "Establecimientos de salud": "salud", "Áreas Públicas": "areas", Otros: "otros" };
    const tipos = Object.entries(datos.series).map(([nombre, valores], indice) => ({
      nombre, base: valores[i] ?? 0, clave: claves[nombre] ?? `tipo-${indice + 1}`,
    }));
    const base = tipos.reduce((suma, tipo) => suma + tipo.base, 0);
    if (base <= 0) {
      baseSimulador.textContent = "El año base no tiene toneladas por procedencia disponibles.";
      return;
    }
    baseSimulador.textContent = `Año base ${anio} · ${fmt(base)} t recolectadas a nivel nacional, sumadas por tipo de procedencia.`;
    const decimal = new Intl.NumberFormat("es-BO", { maximumFractionDigits: 2 });
    const toneladas = (valor) => decimal.format(valor) + " t";
    const porcentaje = (valor) => decimal.format(valor) + " %";
    const params = new URLSearchParams(window.location.search);

    const sliders = $("#sliders");
    sliders.innerHTML = tipos.map(({ nombre, base: total, clave }) => `<div class="simulador-tipo">
      <div>
        <label for="reduccion-${clave}">${nombre}</label>
        <p class="nota" id="base-${clave}">${fmt(total)} t · ${porcentaje(total / base * 100)} del total de ${anio}</p>
      </div>
      <output id="valor-${clave}" for="reduccion-${clave}"></output>
      <div class="simulador-rango">
        <button type="button" data-tipo="${clave}" data-paso="-1" aria-label="Reducir ${nombre} un punto porcentual">−</button>
        <input type="range" id="reduccion-${clave}" min="0" max="100" step="1" value="0" aria-describedby="base-${clave}">
        <button type="button" data-tipo="${clave}" data-paso="1" aria-label="Aumentar ${nombre} un punto porcentual">+</button>
      </div>
    </div>`).join("");
    const controles = new Map(tipos.map(({ clave }) => [clave, $("#reduccion-" + clave)]));
    for (const [clave, control] of controles) {
      const valor = Number(params.get(clave));
      control.value = Number.isInteger(valor) && valor >= 0 && valor <= 100 ? valor : 0;
    }

    const capacidadBase = 10;
    const campos = [
      { clave: "camion", input: $("#camion"), error: $("#errorCamionSim"), valido: (v) => v > 0 && Number.isFinite(base / v) },
      { clave: "meta", input: $("#metaSim"), error: $("#errorMetaSim"), valido: (v) => v >= 0 && v <= 100, opcional: true },
      { clave: "costo", input: $("#costoSim"), error: $("#errorCostoSim"), valido: (v) => v >= 0 && Number.isFinite(base * v), opcional: true },
    ];
    for (const { clave, input, valido } of campos) {
      const valor = params.get(clave);
      if (valor?.trim() && Number.isFinite(Number(valor)) && valido(Number(valor))) input.value = Number(valor);
    }

    const estadoEnlace = $("#estadoEnlaceSim"), campoEnlace = $("#enlaceSim");
    let escenario;
    const leerCampo = ({ input, error, valido, opcional }) => {
      const vacio = input.value === "", valor = input.valueAsNumber;
      const correcto = !input.validity.badInput && (vacio ? opcional : Number.isFinite(valor) && valido(valor));
      error.hidden = Boolean(correcto);
      input.setAttribute("aria-invalid", String(!correcto));
      if (correcto) input.removeAttribute("aria-describedby");
      else input.setAttribute("aria-describedby", error.id);
      return correcto && !vacio ? valor : null;
    };

    const calcular = () => {
      const filas = tipos.map((tipo) => {
        const reduccion = controles.get(tipo.clave).valueAsNumber;
        const ahorro = tipo.base * reduccion / 100;
        $("#valor-" + tipo.clave).textContent = porcentaje(reduccion);
        return { ...tipo, reduccion, ahorro, restante: tipo.base - ahorro };
      });
      const ahorro = filas.reduce((suma, fila) => suma + fila.ahorro, 0);
      const reduccion = ahorro / base * 100;
      const [capacidad, meta, costo] = campos.map(leerCampo);
      const viajes = capacidad == null ? null : ahorro / capacidad;
      const viajesMes = viajes == null ? null : viajes / 12;
      escenario = { filas, ahorro, reduccion, capacidad, meta, costo };
      const invalido = campos.some(({ error }) => !error.hidden);
      $("#copiarEscenario").disabled = invalido;
      $("#exportarEscenario").disabled = invalido;

      $("#ahorroSim").textContent = toneladas(ahorro);
      $("#porcentajeSim").textContent = porcentaje(reduccion);
      $("#viajesAnioSim").textContent = viajes == null ? "—" : decimal.format(viajes);
      $("#viajesMesSim").textContent = viajesMes == null ? "—" : decimal.format(viajesMes);
      const equivalencia = viajes == null ? "" : ` Equivale a ${decimal.format(viajes)} viajes de camión al año, un promedio de ${decimal.format(viajesMes)} al mes.`;
      $("#resumenSim").textContent = `Con este escenario se dejarían de recolectar ${toneladas(ahorro)} al año, un ${porcentaje(reduccion)} del total.${equivalencia}`;

      const resultadoMeta = $("#resultadoMetaSim"), resultadoCosto = $("#resultadoCostoSim");
      resultadoMeta.hidden = meta == null;
      resultadoCosto.hidden = costo == null;
      if (meta != null) {
        const diferencia = ahorro - base * meta / 100;
        const metaTexto = `Meta del ${porcentaje(meta)}.`;
        resultadoMeta.textContent = Math.abs(diferencia) < .005 ? `${metaTexto} Alcanzada.` :
          diferencia > 0 ? `${metaTexto} Se supera por ${toneladas(diferencia)}.` :
            `${metaTexto} Faltan ${toneladas(-diferencia)} de reducción para alcanzarla.`;
      }
      if (costo != null) {
        resultadoCosto.textContent = `Ahorro económico estimado de Bs ${decimal.format(ahorro * costo)} al año, con el costo por tonelada indicado.`;
      }

      $("#desgloseSim").innerHTML = filas.map(({ nombre, reduccion, ahorro, restante }) => `<div class="simulador-barra-tipo">
        <strong>${nombre}</strong>
        <div class="simulador-barra" aria-hidden="true"><span style="width:${reduccion}%"></span></div>
        <span>Evitado ${toneladas(ahorro)} · Restante ${toneladas(restante)}</span>
      </div>`).join("");
      estadoEnlace.textContent = "";
      campoEnlace.hidden = true;
    };

    const guardarURL = () => {
      if (campos.some(({ error }) => !error.hidden)) return window.location.href;
      const url = new URL(window.location.href);
      const { filas, capacidad, meta, costo } = escenario;
      const parametros = [
        ...filas.map((fila) => [fila.clave, fila.reduccion || null]),
        ["camion", capacidad === capacidadBase ? null : capacidad], ["meta", meta], ["costo", costo],
      ];
      for (const [clave, valor] of parametros) {
        if (valor == null) url.searchParams.delete(clave);
        else url.searchParams.set(clave, valor);
      }
      if (url.href !== window.location.href) window.history.replaceState(window.history.state, "", url);
      return url.href;
    };

    sliders.addEventListener("input", calcular);
    sliders.addEventListener("change", guardarURL);
    sliders.addEventListener("click", (evento) => {
      const boton = evento.target.closest("button[data-paso]");
      if (!boton) return;
      const control = controles.get(boton.dataset.tipo);
      control.value = Math.max(0, Math.min(100, control.valueAsNumber + Number(boton.dataset.paso)));
      calcular();
      guardarURL();
    });
    for (const { input } of campos) {
      input.addEventListener("input", calcular);
      input.addEventListener("change", guardarURL);
    }
    const presets = { conservador: 5, ambicioso: 25, restablecer: 0 };
    $("#presetsSimulador").addEventListener("click", (evento) => {
      const boton = evento.target.closest("button[data-escenario]");
      if (!boton) return;
      const preset = boton.dataset.escenario;
      for (const [clave, control] of controles) {
        control.value = preset === "domiciliarios" ? (clave === "dom" ? 20 : 0) : presets[preset];
      }
      if (preset === "restablecer") {
        $("#camion").value = capacidadBase;
        $("#metaSim").value = $("#costoSim").value = "";
      }
      calcular();
      guardarURL();
    });
    $("#copiarEscenario").addEventListener("click", async () => {
      const enlace = guardarURL();
      try {
        await navigator.clipboard.writeText(enlace);
        estadoEnlace.textContent = "Enlace del escenario copiado.";
      } catch {
        campoEnlace.value = enlace;
        campoEnlace.hidden = false;
        campoEnlace.select();
        estadoEnlace.textContent = "El enlace está seleccionado para copiar.";
      }
    });
    $("#exportarEscenario").addEventListener("click", () => {
      const { filas, ahorro, reduccion, capacidad, meta, costo } = escenario;
      const redondear = (numero) => numero.toFixed(2);
      const prepararFila = ({ nombre, base, reduccion, ahorro, restante }) => [
        nombre, anio, base, redondear(reduccion), redondear(ahorro), redondear(restante), capacidad ?? "",
        capacidad == null ? "" : redondear(ahorro / capacidad),
        capacidad == null ? "" : redondear(ahorro / capacidad / 12),
        meta ?? "", costo ?? "", costo == null ? "" : redondear(ahorro * costo),
      ];
      const csv = [
        ["Tipo", "Año base", "Toneladas base", "Reducción (%)", "Toneladas evitadas", "Toneladas restantes", "Capacidad (t)",
          "Viajes por año", "Viajes por mes", "Meta (%)", "Costo (Bs/t)", "Ahorro estimado (Bs)"],
        ...filas.map(prepararFila),
        prepararFila({ nombre: "Total", base, reduccion, ahorro, restante: base - ahorro }),
      ].map((fila) => fila.map((valor) => '"' + String(valor).replaceAll('"', '""') + '"').join(",")).join("\r\n");
      const archivo = URL.createObjectURL(new Blob(["\ufeff", csv], { type: "text/csv;charset=utf-8" }));
      const enlace = document.createElement("a");
      enlace.href = archivo;
      enlace.download = `escenario-residuos-${anio}.csv`;
      enlace.click();
      setTimeout(() => URL.revokeObjectURL(archivo), 0);
    });

    calcular();
    guardarURL();
    const layout = $("#escenarioSimulador"), cabecera = $("header");
    if (cabecera && typeof ResizeObserver === "function") {
      new ResizeObserver(() => layout.style.setProperty("--offset-simulador", (cabecera.offsetHeight + 16) + "px")).observe(cabecera);
    }
    layout.hidden = false;
    $("#volumenSimulador").hidden = false;
  },
  async reporte() {
    const c = document.body.dataset.ciudad;
    const cat = encodeURIComponent(c);
    $("#titulo").textContent = "Reporte: " + c;
    $("#pdf").addEventListener("click", () => window.print());
    const [[s], p, d] = await Promise.all([
      get(`/api/serie?cats=${cat}&agg=anual`),
      get(`/api/pronostico?cat=${cat}&meses=12`),
      get(c === "Total" ? "/api/composicion" : `/api/ciudad-tipo?ciudad=${cat}`),
    ]);
    $("#pieReporte").textContent = "Fuente: datos del INE. El Total nacional incluye Cobija y la serie de Sucre empieza en 2015.";
    if (s?.y.length) {
      const ult = s.y.at(-1), prev = s.y.at(-2), max = Math.max(...s.y);
      const imax = s.y.indexOf(max);
      const kpis = [[fmt(ult) + " t", `Recolectado en ${s.x.at(-1)}`]];
      if (prev > 0) kpis.push([((ult / prev - 1) * 100).toFixed(1) + " %", `Variación vs ${s.x.at(-2)}`]);
      kpis.push([fmt(max) + " t", `Máximo histórico (${s.x[imax]})`]);
      $("#kpisC").innerHTML = kpis.map(([a, b]) => `<div class="kpi"><b>${a}</b><span>${b}</span></div>`).join("");
      const omitidos = s.omitidos?.length ? ` Años omitidos por tener menos de 12 meses de registro: ${s.omitidos.join(", ")}.` : "";
      $("#resumenSerie").textContent = `Hay ${s.x.length} años con registro completo entre ${s.x[0]} y ${s.x.at(-1)}. En el primero se recolectaron ${fmt(s.y[0])} t y en el último, ${fmt(ult)} t.${omitidos}`;
      dibujar("rSerie", { type: "bar", data: { labels: s.x, datasets: [{ label: c + " (t)", data: s.y, backgroundColor: COLORES[0] }] }, options: { scales: ejes } });
    } else {
      $("#rSerie").hidden = true;
      $("#resumenSerie").textContent = "No hay años con 12 meses de registro para esta serie.";
    }

    const tipos = Object.entries(d.series);
    const ultimo = d.anios.findLastIndex((_, i) => tipos.some(([, valores]) => valores[i] != null));
    if (ultimo >= 0) {
      const valores = tipos.map(([tipo, serie]) => [tipo, serie[ultimo] ?? 0]).sort((a, b) => b[1] - a[1]);
      const total = valores.reduce((suma, [, ton]) => suma + ton, 0);
      const [tipo, mayor] = valores[0];
      if (total > 0) {
        const proporcion = new Intl.NumberFormat("es-BO", { style: "percent", maximumFractionDigits: 1 }).format(mayor / total);
        $("#resumenTipos").textContent = `En ${d.anios[ultimo]}, ${tipo} fue la procedencia con mayor volumen: ${fmt(mayor)} t, equivalentes al ${proporcion} del total por procedencia.`;
      } else {
        $("#resumenTipos").textContent = `En ${d.anios[ultimo]} los tipos registrados suman 0 toneladas.`;
      }
      dibujar("rTipos", { type: "bar", data: { labels: d.anios, datasets: tipos.map(([tipo, valores], i) => ({ label: tipo, data: valores, backgroundColor: COLORES[i] })) }, options: { scales: { x: { stacked: true }, y: { stacked: true } } } });
    } else {
      $("#rTipos").hidden = true;
      $("#resumenTipos").textContent = "No hay datos de recolección por procedencia para esta serie.";
    }
    if (p.error) {
      $("#figuraPronReporte").hidden = true;
      return;
    }
    dibujar("rPron", { type: "line", data: { labels: [...p.hist.x.slice(-24), ...p.pred.x], datasets: [{ label: "Histórico", data: [...p.hist.y.slice(-24), ...new Array(p.pred.x.length).fill(null)], borderColor: COLORES[0], pointRadius: 0 }, { label: "Pronóstico", data: [...new Array(Math.min(24, p.hist.y.length)).fill(null), ...p.pred.y], borderColor: COLORES[1], borderDash: [6, 4], pointRadius: 0 }] } });
  },
});

document.querySelector("#imprimir")?.addEventListener("click", () => window.print());
document.querySelector("#imprimirPlan")?.addEventListener("click", () => {
  const body = document.body;
  body.classList.add("imprime-plan");
  window.addEventListener("afterprint", () => body.classList.remove("imprime-plan"), { once: true });
  window.print();
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
