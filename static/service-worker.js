self.addEventListener("install", (event) => {
  console.log("✅ Service Worker установлен");
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  console.log("🚀 Service Worker активирован");
});

// ❌ Не кэшируем — всё всегда идёт из сети
self.addEventListener("fetch", (event) => {
  event.respondWith(
    fetch(event.request).catch(() => {
      return new Response(
        "<h1 style='text-align:center;margin-top:50px;font-family:sans-serif;'>⚠️ Требуется интернет-соединение</h1>",
        { headers: { "Content-Type": "text/html" } }
      );
    })
  );
});
