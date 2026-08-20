// Checkbox que prende/apaga el fondo animado (hook MetroBg). El estado
// vive en localStorage ("mapo:bg-animation"), lo mismo que ya lee
// metro_bg.js, para que ambos queden sincronizados sin ida y vuelta al
// servidor (es una preferencia puramente de cliente).

export const BgAnimationToggle = {
  mounted() {
    this.el.checked = localStorage.getItem("mapo:bg-animation") !== "off"

    this.el.addEventListener("change", () => {
      const enabled = this.el.checked
      localStorage.setItem("mapo:bg-animation", enabled ? "on" : "off")
      window.dispatchEvent(new CustomEvent("mapo:toggle-bg-animation", {detail: {enabled}}))
    })
  },
}
