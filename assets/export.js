window.dash_clientside = Object.assign({}, window.dash_clientside, {
  dashboard: {
    exportCsv: async function (clicks, ...filters) {
      if (!clicks || window.dashboardExporting) return window.dash_clientside.no_update;
      window.dashboardExporting = true;
      const setStatus = (message) => window.dash_clientside.set_props("export-status", {children: message});
      const button = document.getElementById("btn-download");
      button.disabled = true;
      try {
        const parts = [];
        let offset = 0;
        let more = true;
        while (more) {
          setStatus(`Preparando exportação… ${offset} anúncios processados.`);
          const response = await fetch("/api/export", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({filters, offset}),
          });
          if (!response.ok) throw new Error(`Exportação falhou (HTTP ${response.status}).`);
          const hasMore = response.headers.get("X-Export-Has-More");
          if (hasMore !== "0" && hasMore !== "1") throw new Error("Resposta de exportação incompleta.");
          parts.push(await response.text());
          more = hasMore === "1";
          offset += 100;
        }
        const url = URL.createObjectURL(new Blob(parts, {type: "text/csv;charset=utf-8"}));
        const link = document.createElement("a");
        link.href = url;
        link.download = "vagas_filtradas.csv";
        document.body.appendChild(link);
        link.click();
        link.remove();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
        return "CSV pronto para download.";
      } catch (error) {
        console.error("Erro ao exportar CSV:", error);
        return "Não foi possível exportar. Verifique a conexão e tente novamente.";
      } finally {
        window.dashboardExporting = false;
        button.disabled = false;
      }
    },
  },
});
