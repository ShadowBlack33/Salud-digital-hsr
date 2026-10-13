// Interruptor de los datos de demostración del front.
//
// Con VITE_DATOS_DEMO=false (al compilar) el front NO reemplaza una ruta
// inexistente con datos de ejemplo: muestra el error real, oculta el panel de
// demostración y no simula eventos. Úsese para la sustentación una vez que los
// módulos reales estén desplegados, para que nada simulado se confunda con lo
// implementado. El tester automático habla directo con la API: nunca ve estos datos.
export const DATOS_DEMO = import.meta.env.VITE_DATOS_DEMO !== "false";
