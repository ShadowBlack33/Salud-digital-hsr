import { useEffect, useRef, useState } from "react";

// La idea central (igual que en el notebook): para cada píxel de la imagen
// ORIGINAL calculamos un valor nuevo según el brillo y el contraste que
// elija el usuario, y lo pintamos en un segundo canvas -- nunca se pierde
// la imagen original, cada ajuste parte siempre de los datos originales.
export default function VisorImagen({ url, onCerrar }) {
  const canvasOriginal = useRef(null);
  const canvasAjustado = useRef(null);
  const [brillo, setBrillo] = useState(0);       // -100 .. 100
  const [contraste, setContraste] = useState(0); // -100 .. 100
  const [datosOriginales, setDatosOriginales] = useState(null);

  useEffect(() => {
    const img = new Image();
    img.onload = () => {
      const c = canvasOriginal.current;
      c.width = img.width;
      c.height = img.height;
      const ctx = c.getContext("2d");
      ctx.drawImage(img, 0, 0);
      setDatosOriginales(ctx.getImageData(0, 0, c.width, c.height));

      const c2 = canvasAjustado.current;
      c2.width = img.width;
      c2.height = img.height;
    };
    img.src = url;
  }, [url]);

  useEffect(() => {
    if (!datosOriginales) return;
    const c2 = canvasAjustado.current;
    const ctx2 = c2.getContext("2d");
    const salida = ctx2.createImageData(datosOriginales.width, datosOriginales.height);

    const factorContraste = (259 * (contraste + 255)) / (255 * (259 - contraste));
    const src = datosOriginales.data;
    const dst = salida.data;

    for (let i = 0; i < src.length; i += 4) {
      for (let canal = 0; canal < 3; canal++) {
        let v = src[i + canal] + brillo;               // brillo: suma directa
        v = factorContraste * (v - 128) + 128;          // contraste: aleja/acerca del gris medio
        dst[i + canal] = Math.max(0, Math.min(255, v));
      }
      dst[i + 3] = src[i + 3]; // canal alfa, sin cambios
    }
    ctx2.putImageData(salida, 0, 0);
  }, [datosOriginales, brillo, contraste]);

  return (
    <div className="visor-overlay" onClick={onCerrar}>
      <div className="visor-ventana" onClick={(e) => e.stopPropagation()}>
        <button className="visor-cerrar" onClick={onCerrar}>✕</button>

        <canvas ref={canvasOriginal} style={{ display: "none" }} />
        <canvas ref={canvasAjustado} className="visor-canvas" />

        <div className="visor-controles">
          <label>
            Contraste
            <input type="range" min="-100" max="100" value={contraste}
                  onChange={(e) => setContraste(Number(e.target.value))} />
          </label>
          <label>
            Brillo
            <input type="range" min="-100" max="100" value={brillo}
                  onChange={(e) => setBrillo(Number(e.target.value))} />
          </label>
          <button className="visor-reset" onClick={() => { setBrillo(0); setContraste(0); }}>
            Restablecer
          </button>
        </div>
      </div>
    </div>
  );
}
