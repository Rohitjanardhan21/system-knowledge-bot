<!DOCTYPE html>
<html>
<body>

<h1>System Knowledge Bot — Truth Page</h1>

<pre id="out">Loading…</pre>

<script>
fetch("/gui/current")
  .then(r => r.json())
  .then(d => {
    document.getElementById("out").textContent =
      JSON.stringify(d, null, 2);
    console.log("TRUTH:", d);
  })
  .catch(e => {
    document.getElementById("out").textContent = e.toString();
  });
</script>

</body>
</html>
