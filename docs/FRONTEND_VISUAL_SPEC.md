# DevTrack — Especificación visual del frontend

## 1. Propósito y alcance

Este documento define la dirección visual y los criterios de interfaz para el
futuro frontend de DevTrack, previsto con React, TypeScript y Tailwind CSS.
Sirve como referencia para diseñar e implementar las primeras pantallas sin
presuponer funcionalidades o contratos que el backend no ofrezca.

La identidad visual se denomina **Technical Precision**. La especificación
cubre fundamentos visuales, temas, dashboard, login, adaptación responsive,
accesibilidad, estados de interfaz e integración con el backend. No define
arquitectura de despliegue, un sistema de diseño ya implementado ni nuevas
funcionalidades de producto.

## 2. Identidad: Technical Precision

### Dirección visual

- Estética **Industrial / Engineering**: precisa, sobria, estructurada y
  orientada al trabajo técnico.
- Apariencia profesional y elegante, con personalidad propia; priorizar
  claridad, jerarquía y utilidad sobre ornamentación.
- Usar superficies limpias, divisiones nítidas, alineación consistente y
  acentos de latón de forma medida.
- Evitar dashboards SaaS genéricos, degradados morados, neones, efectos
  gaming, sombras excesivas y decoración que compita con los datos.
- No utilizar color como único medio para comunicar estado, prioridad o
  selección.

### Tono de la interfaz

Los textos de interfaz deben ser directos, breves y consistentes. Las acciones
deben nombrar el resultado esperado; los errores deben explicar qué ocurrió y,
cuando sea posible, cómo continuar. Mantener el idioma de la interfaz uniforme
según la localización que se decida para el producto.

## 3. Paleta y tokens de color

| Token | Valor | Uso orientativo |
|---|---|---|
| Graphite | `#20282B` | Navegación, texto principal en tema claro y superficies profundas |
| Steel | `#66757A` | Texto secundario, iconos y elementos de baja prominencia |
| Brass | `#B58A52` | Acento de marca, selección o acción destacada, con uso contenido |
| Ivory | `#F1F0EA` | Fondo principal del tema claro |
| Paper | `#FFFFFF` | Superficies y campos del tema claro |
| Mist | `#E1E5E2` | Bordes suaves, divisores y superficies sutiles |
| Success | `#39765B` | Confirmación y estado satisfactorio |
| Warning | `#B17B32` | Advertencias y atención requerida |
| Error | `#B34D47` | Errores y acciones destructivas |
| Information | `#426D8A` | Información y estados neutrales destacados |

En la implementación, exponer estos valores mediante tokens semánticos (por
ejemplo, fondo, superficie, texto, borde, acento y estado) para que los temas
puedan asignar valores coherentes sin acoplar cada componente a un color
concreto.

Los colores son una base visual, no una certificación de accesibilidad.
**Verificar las combinaciones reales de texto, fondo, iconos y estados con
criterios WCAG vigentes; ajustar los valores o el uso de los colores cuando
sea necesario para alcanzar los niveles de contraste requeridos.** Comprobar
estados normales, hover, foco, deshabilitado y selección por separado. No
suponer que un color semántico sirve como texto sobre cualquier superficie.

## 4. Tipografía y jerarquía

- **Inter** para títulos, cuerpo, controles, etiquetas y contenido general.
- **IBM Plex Mono** para identificadores, métricas y datos técnicos breves,
  como códigos o marcas temporales compactas. No usarla para párrafos largos.
- Establecer una escala tipográfica pequeña y consistente, con jerarquía
  perceptible entre título de página, encabezados de sección, texto normal,
  metadatos y ayudas.
- Usar pesos tipográficos para estructurar el contenido; no depender solo del
  tamaño ni abusar de mayúsculas.
- Mantener una longitud de línea y altura de línea cómodas para lectura.
- Definir alternativas de fuente del sistema para que la interfaz siga siendo
  legible si las fuentes web no están disponibles.

## 5. Espaciado, formas e iconografía

- Utilizar una escala de espaciado en **múltiplos de 4 px**.
- Aplicar radios de **8–12 px** a tarjetas y contenedores agrupadores.
- Aplicar radios de **5–8 px** a campos, botones y controles pequeños.
- Usar tarjetas solo cuando agrupen contenido relacionado; evitar convertir
  cada dato o sección en una tarjeta independiente.
- Mantener alineaciones, alturas de controles y separaciones consistentes.
- Usar iconografía de una única familia o sistema, con grosor, tamaño y
  alineación coherentes. Los iconos que ejecuten acciones deben tener nombre
  accesible; si no son universalmente reconocibles, acompañarlos de texto.
- Reservar las sombras para indicar elevación o superposición real. Preferir
  bordes y contraste de superficie para la estructura ordinaria.

## 6. Temas

La interfaz debe contemplar tema claro, tema oscuro y preferencia del sistema.
La preferencia del sistema es una opción seleccionable; el mecanismo concreto
de persistencia de la preferencia queda pendiente de la arquitectura del
frontend.

### Tema claro

- Fondo principal marfil (`Ivory`).
- Superficies de contenido blancas (`Paper`).
- Navegación lateral grafito (`Graphite`), con texto e iconos de contraste
  suficiente.
- Texto principal oscuro; texto secundario claramente distinguible y nunca
  demasiado tenue para contenido esencial.
- Bordes y divisores sutiles basados en `Mist`.
- Usar `Brass` como acento con moderación y comprobar su contraste en cada
  combinación de texto o icono.

### Tema oscuro

- Usar `Graphite` como base y superficies derivadas de grafito con ligeras
  variaciones de luminosidad para distinguir niveles.
- Evitar negro absoluto, fondos completamente negros, neones y contrastes
  deslumbrantes.
- Usar texto claro con contraste suficiente; distinguir texto principal,
  secundario y deshabilitado sin volver ilegible el secundario.
- Adaptar bordes y divisores para que se perciban sobre fondos oscuros sin
  formar líneas agresivas.
- Ajustar `Brass` y los colores semánticos si su luminosidad o contraste no
  son adecuados en superficies oscuras.

### Criterios comunes a ambos temas

- Definir pares semánticos de fondo/superficie, texto, borde, acento y estados
  para cada tema.
- Los estados de éxito, advertencia, error e información deben mantener un
  significado estable en ambos temas, con variantes de superficie y texto
  legibles.
- Acompañar los estados por texto, icono o forma; no comunicar su significado
  únicamente mediante color.
- Revisar contraste y foco en ambos temas y en todos los estados interactivos.

## 7. Dashboard

### Estructura

- Cabecera de página con el título **“Centro de operaciones”**.
- Navegación lateral expandible y contraíble, con las secciones:
  **Resumen, Proyectos, Tareas, Equipo, Informes y Ajustes**.
- En modo compacto, conservar etiquetas accesibles y ofrecer nombres
  perceptibles para los iconos, por ejemplo mediante texto auxiliar o
  información emergente accesible por teclado.
- Presentar el contenido en una cuadrícula que priorice las acciones y datos
  relevantes, sin llenar la pantalla de tarjetas.

### Resumen e indicadores

El resumen puede presentar indicadores para:

- Proyectos activos.
- Tareas pendientes.
- Progreso global.
- Elementos que requieren atención.

La zona analítica contempla visualizaciones de evolución temporal, progreso
por proyecto y distribución por estado. La página también incluye actividad
reciente y una sección personal **“Mis tareas”**.

**Todos los indicadores, gráficas y elementos de actividad deben derivarse de
datos y endpoints reales disponibles en el backend. No usar estadísticas
ficticias, datos de demostración ni valores inventados en producción.** Si un
indicador no se puede calcular con los contratos existentes, ocultarlo,
mostrarlo como no disponible o plantear la necesidad como una decisión de
producto/API antes de implementarlo. No inferir que existe un endpoint por el
hecho de que una visualización aparezca en esta especificación.

Los gráficos deben incluir títulos, contexto temporal cuando aplique,
etiquetado comprensible y una alternativa textual o tabular accesible. Evitar
depender únicamente de diferencias de color para distinguir series o estados.

## 8. Login

### Composición

- En escritorio, usar dos zonas: panel de marca en grafito y formulario sobre
  fondo marfil.
- El panel derecho conservará el fondo marfil (`Ivory`, `#F1F0EA`), con un
  formulario limpio y los mismos controles compartidos con el resto de
  DevTrack.
- El formulario debe priorizar legibilidad, etiquetas persistentes y una
  acción principal inequívoca.
- En móvil, pasar a una sola columna y mantener el formulario como contenido
  prioritario, sin exigir desplazamiento horizontal.
- Reutilizar colores, tipografía, controles, radios y estados del dashboard.

### Panel de marca e ilustración

- En escritorio, el panel izquierdo tendrá fondo grafito (`Graphite`,
  `#20282B`) y mostrará el nombre de marca **DevTrack** junto a un lema breve
  y sobrio, coherente con la identidad “Technical Precision”.
- Reservar en el panel un área de composición para integrar posteriormente una
  ilustración propia sin cambiar la estructura de dos zonas ni interferir con
  el formulario.
- La ilustración principal se basará en un plano técnico minimalista de
  inspiración industrial y arquitectónica: líneas finas, geometría isométrica
  o estructuras geométricas, líneas de referencia, cotas y pequeños detalles
  en latón (`Brass`, `#B58A52`).
- Mantener una ejecución elegante, precisa y sobria, con suficiente espacio
  negativo. Evitar gráficos estadísticos, dashboards en miniatura, elementos
  HUD de ciencia ficción, neones, degradados, ilustraciones genéricas y
  ornamentación excesiva.
- La ilustración es decorativa: no debe simular métricas ni representar datos
  reales.
- Si posteriormente se incorpora como imagen o SVG, mantener su presentación
  responsive, proporcionar una alternativa accesible apropiada (o marcarla
  como decorativa para tecnologías de asistencia cuando no aporte información)
  y cargarla de forma que no bloquee la disponibilidad ni el uso del
  formulario.
- En móvil, el formulario seguirá teniendo prioridad y el panel de marca se
  compactará sin provocar desplazamiento horizontal.

### Integración con el contrato existente

- El endpoint confirmado para iniciar sesión es `POST /auth/login`.
- Envía `username` y `password` como formulario URL-encoded compatible con
  OAuth2 (`application/x-www-form-urlencoded`), no como JSON.
- La respuesta confirmada contiene `access_token` y `token_type` (`bearer`).
- Para consultar el perfil autenticado existe `GET /users/me`, usando
  `Authorization: Bearer <access_token>`.
- Presentar de forma comprensible los errores observados: credenciales
  incorrectas (`401`) y cuenta desactivada (`403`); considerar también errores
  de red y validación sin ocultar su causa.
- El token dura 30 minutos según el comportamiento actual del backend. No hay
  endpoint de renovación ni endpoint dedicado de logout confirmados. No
  diseñar llamadas a rutas inexistentes. La estrategia de almacenamiento del
  token, expiración y cierre local/remoto requiere decisión antes de
  implementar autenticación de producción.
- El registro no forma parte del flujo de login: `POST /auth/register` acepta
  JSON y devuelve el perfil creado (`201`), no un token.

## 9. Diseño responsive

Los puntos de quiebre definitivos se establecerán al implementar y probar los
layouts; no hay una escala responsive preexistente en el repositorio. Como
criterio inicial:

- **Escritorio:** navegación lateral expandida por defecto; dashboard en varias
  columnas y analítica distribuida en función del espacio disponible.
- **Tablet:** permitir contraer la navegación lateral y reducir columnas sin
  comprimir texto, controles o gráficos hasta volverlos ilegibles.
- **Móvil:** una columna, navegación accesible mediante un patrón compacto
  apropiado, controles táctiles cómodos y prioridad al contenido principal.
  El patrón concreto (menú desplegable u otra variante) se decidirá con el
  prototipo responsive.

En todos los anchos:

- Evitar overflow horizontal de página; permitir desplazamiento horizontal
  solo en elementos cuyo contenido lo justifique y con indicación accesible.
- Las tablas y gráficas deben transformarse, desplazarse de forma controlada
  o ofrecer una presentación alternativa; no recortar información esencial.
- Reorganizar métricas y secciones antes que reducir excesivamente su tamaño.
- Probar con zoom, textos largos, etiquetas extensas, contenido vacío y
  traducciones que ocupen más espacio.

## 10. Accesibilidad

- Usar estructura semántica, jerarquía de encabezados coherente y regiones de
  navegación y contenido identificables.
- Asociar cada campo con una etiqueta visible; no usar el placeholder como
  sustituto de la etiqueta. Comunicar formato, obligatoriedad y errores junto
  al campo correspondiente.
- Todas las funciones deben ser operables mediante teclado. Mantener un orden
  de foco lógico y un indicador de foco visible en ambos temas.
- Los menús, navegación contraída, diálogos, gráficos y controles
  iconográficos deben exponer nombres, roles y estados accesibles.
- Mantener contraste suficiente para texto, componentes y foco, verificando
  las combinaciones reales de cada tema.
- No depender exclusivamente del color, posición, sonido o movimiento para
  transmitir información.
- Respetar la preferencia de movimiento reducido y evitar animaciones
  necesarias para comprender el estado.
- Las actualizaciones asíncronas importantes deben comunicarse de forma que
  tecnologías de asistencia puedan detectarlas sin interrumpir innecesariamente
  la lectura.
- Probar navegación por teclado y lectores de pantalla en los flujos críticos
  además de la validación automatizada.

## 11. Estados de interfaz

Cada pantalla y operación asíncrona debe definir estados coherentes:

- **Carga:** indicar qué región se está cargando; evitar saltos grandes de
  layout y no bloquear interacciones no relacionadas.
- **Error:** explicar el problema con lenguaje claro y mostrar una acción de
  recuperación solo cuando sea segura y pertinente. Mantener códigos y
  significado del backend, sin presentar errores técnicos o secretos al
  usuario.
- **Vacío:** distinguir entre ausencia legítima de datos y falta de
  configuración o permisos. Ofrecer una acción contextual únicamente si
  existe una operación real para realizarla.
- **Éxito:** confirmar brevemente que la acción terminó y actualizar la vista
  con la respuesta real del servidor.
- **Deshabilitado:** comunicar visualmente y mediante tecnología de asistencia
  por qué una acción no está disponible cuando esa razón sea conocida.

Los estados deben ser consistentes entre páginas y legibles en ambos temas.
No sustituir silenciosamente errores por colecciones vacías ni mostrar
contenido de ejemplo como si fueran datos del usuario.

## 12. Límites y decisiones pendientes

- Este documento es una especificación visual; no crea una aplicación ni
  determina dependencias, componentes o arquitectura ejecutable.
- La estructura de frontend prevista es React, TypeScript y Tailwind CSS, pero
  todavía no existe código ni configuración de estas tecnologías en el
  repositorio.
- La lista de secciones del dashboard expresa la composición visual deseada,
  no confirma que todas las funciones o datos necesarios estén disponibles
  mediante la API actual.
- No inventar endpoints, campos, permisos, agregaciones, estados de dominio ni
  comportamientos de autenticación. Verificar cada contrato en el backend
  durante la implementación.
- No están definidos aún los orígenes de frontend para CORS, la URL base de
  API por entorno, la localización, el comportamiento de persistencia del
  tema, ni la política de almacenamiento y revocación del token.
- Contrastar las visualizaciones propuestas con endpoints y datos disponibles.
  Si falta soporte, registrar la necesidad y solicitar una decisión antes de
  ampliar contratos o alcance.
- Verificar la paleta mediante pruebas de contraste y ajustar tokens si es
  necesario para la accesibilidad.
