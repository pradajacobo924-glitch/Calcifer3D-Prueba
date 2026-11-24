const toggle = document.getElementById("menuToggle");
const nav = document.getElementById("navLinks");

if (toggle && nav) {
    toggle.addEventListener("click", () => {
        nav.classList.toggle("active");
    });
}

// Cargar dinámicamente los productos de la base de datos MySQL en la tienda
async function cargarProductosCatalogo() {
    const grid = document.querySelector(".productos-grid");
    if (!grid) return;

    try {
        const response = await fetch("/api/productos");
        const result = await response.json();

        if (result.ok && Array.isArray(result.data) && result.data.length > 0) {
            grid.innerHTML = result.data.map(prod => {
                const fotoSrc = prod.foto 
                    ? (prod.foto.startsWith("/") ? prod.foto : `/${prod.foto}`)
                    : "img/producto1.png";
                
                const precio = Number(prod.precio_fisico || prod.precio_redes || prod.precio_mercadolibre || 0);
                const precioFormateado = precio > 0 
                    ? `$${precio.toLocaleString("es-CO")}` 
                    : "Consultar precio";

                return `
                    <div class="producto-card">
                        <img src="${fotoSrc}" alt="${prod.nombre || 'Producto'}" style="width:100%; height:220px; object-fit:cover; border-radius:8px;">
                        <div class="producto-info">
                            <h3>${prod.nombre || 'Sin nombre'}</h3>
                            ${prod.marca ? `<p style="font-size:0.85rem; color:#888; margin-bottom:6px;">${prod.marca}</p>` : ''}
                            <p class="precio">${precioFormateado}</p>
                            <button type="button">Ver más</button>
                        </div>
                    </div>
                `;
            }).join("");
        }
    } catch (error) {
        console.warn("No se pudieron cargar los productos dinámicos de la BD, manteniendo catálogo base:", error);
    }
}

// Ejecutar de inmediato y también al cargar el DOM
if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", cargarProductosCatalogo);
} else {
    cargarProductosCatalogo();
}
