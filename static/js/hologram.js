(function () {
  function buildScene(container) {
    var W = container.clientWidth || 700;
    var H = container.clientHeight || 340;

    var scene = new THREE.Scene();
    var camera = new THREE.PerspectiveCamera(40, W / H, 0.1, 100);
    camera.position.set(0, 1.35, 4.0);
    camera.lookAt(0, 0.95, 0);

    var renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setSize(W, H);
    renderer.setClearColor(0x000000, 0);
    container.appendChild(renderer.domElement);

    // Small emitter disc, mounted ABOVE the figure (ceiling projector).
    var ringGeo = new THREE.RingGeometry(0.12, 0.22, 48);
    var ringMat = new THREE.MeshBasicMaterial({
      color: 0x00fff2, side: THREE.DoubleSide, transparent: true,
      opacity: 0.6, blending: THREE.AdditiveBlending, depthWrite: false,
    });
    var ring = new THREE.Mesh(ringGeo, ringMat);
    ring.rotation.x = Math.PI / 2;
    ring.position.y = 1.92;
    scene.add(ring);

    var ringGlowGeo = new THREE.RingGeometry(0.02, 0.24, 48);
    var ringGlowMat = new THREE.MeshBasicMaterial({
      color: 0x00fff2, side: THREE.DoubleSide, transparent: true,
      opacity: 0.18, blending: THREE.AdditiveBlending, depthWrite: false,
    });
    var ringGlow = new THREE.Mesh(ringGlowGeo, ringGlowMat);
    ringGlow.rotation.x = Math.PI / 2;
    ringGlow.position.y = 1.925;
    scene.add(ringGlow);

    // Soft light pool on the floor where the beam lands.
    var floorGlowGeo = new THREE.CircleGeometry(0.62, 48);
    var floorGlowMat = new THREE.MeshBasicMaterial({
      color: 0x00fff2, side: THREE.DoubleSide, transparent: true,
      opacity: 0.12, blending: THREE.AdditiveBlending, depthWrite: false,
    });
    var floorGlow = new THREE.Mesh(floorGlowGeo, floorGlowMat);
    floorGlow.rotation.x = -Math.PI / 2;
    floorGlow.position.y = 0.005;
    scene.add(floorGlow);

    // Ceiling-projector light cone: narrow at the emitter, flaring out
    // wide as it descends, sized to fully enclose the figure at every
    // height (shoulders/legs never poke out of the beam).
    var beamGeo = new THREE.CylinderGeometry(0.16, 0.62, 1.95, 24, 1, true);
    var beamMat = new THREE.MeshBasicMaterial({
      color: 0x00fff2, transparent: true, opacity: 0.08, side: THREE.DoubleSide,
      blending: THREE.AdditiveBlending, depthWrite: false,
    });
    var beam = new THREE.Mesh(beamGeo, beamMat);
    beam.position.y = 0.97;
    scene.add(beam);

    var mixer;
    var clock = new THREE.Clock();
    var loader = new THREE.GLTFLoader();

    loader.load(
      'https://cdn.jsdelivr.net/gh/KhronosGroup/glTF-Sample-Models@main/2.0/CesiumMan/glTF-Binary/CesiumMan.glb',
      function (gltf) {
        var model = gltf.scene;

        // Collect target meshes FIRST. Mutating the graph (child.add(...))
        // while model.traverse() is still walking it makes traverse also
        // visit the newly-added nodes -> infinite recursion.
        var meshesToHolofy = [];
        model.traverse(function (child) {
          if (child.isMesh) {
            meshesToHolofy.push(child);
          }
        });

        meshesToHolofy.forEach(function (child) {
          var holoMat = new THREE.MeshBasicMaterial({
            color: 0x39fff2,
            transparent: true,
            opacity: 0.32,
            blending: THREE.NormalBlending,
            depthWrite: false,
            side: THREE.DoubleSide,
            skinning: !!child.isSkinnedMesh,
          });
          child.material = holoMat;

          var wireMat = new THREE.MeshBasicMaterial({
            color: 0xcdfff9, wireframe: true, transparent: true, opacity: 0.4,
            depthWrite: false, skinning: !!child.isSkinnedMesh,
          });
          var WireCtor = child.isSkinnedMesh ? THREE.SkinnedMesh : THREE.Mesh;
          var wireMesh = new WireCtor(child.geometry, wireMat);
          if (child.isSkinnedMesh) {
            wireMesh.bind(child.skeleton, child.bindMatrix);
          }
          child.add(wireMesh);
        });

        scene.add(model);

        if (gltf.animations && gltf.animations.length) {
          mixer = new THREE.AnimationMixer(model);
          mixer.clipAction(gltf.animations[0]).play();
        }
      },
      undefined,
      function (err) {
        console.error("Hologram modeli yuklenemedi (ag/CDN erisimi gerekiyor):", err);
      }
    );

    // Ambient rising particles.
    var particleCount = 220;
    var positions = new Float32Array(particleCount * 3);
    for (var i = 0; i < particleCount; i++) {
      var r = 0.55 + Math.random() * 0.5;
      var theta = Math.random() * Math.PI * 2;
      var y = Math.random() * 1.9;
      positions[i * 3] = r * Math.cos(theta);
      positions[i * 3 + 1] = y;
      positions[i * 3 + 2] = r * Math.sin(theta);
    }
    var particleGeo = new THREE.BufferGeometry();
    particleGeo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    var particleMat = new THREE.PointsMaterial({
      color: 0x9dfff5, size: 0.012, transparent: true, opacity: 0.55,
    });
    var particles = new THREE.Points(particleGeo, particleMat);
    scene.add(particles);

    var composer = new THREE.EffectComposer(renderer);
    composer.addPass(new THREE.RenderPass(scene, camera));
    var bloomPass = new THREE.UnrealBloomPass(new THREE.Vector2(W, H), 0.8, 0.45, 0.25);
    composer.addPass(bloomPass);

    function animate() {
      requestAnimationFrame(animate);
      var delta = clock.getDelta();
      if (mixer) {
        mixer.update(delta * 0.6);
      }
      ring.rotation.z += 0.004;
      ringGlow.rotation.z -= 0.002;
      particles.rotation.y += 0.0012;
      composer.render();
    }
    animate();

    window.addEventListener('resize', function () {
      var newW = container.clientWidth || W;
      var newH = container.clientHeight || H;
      renderer.setSize(newW, newH);
      camera.aspect = newW / newH;
      camera.updateProjectionMatrix();
      composer.setSize(newW, newH);
    });
  }

  function setCaption(text) {
    var captionEl = document.getElementById('holo-caption-text');
    if (captionEl) {
      captionEl.textContent = text;
    }
  }

  window.updateHologramCaption = setCaption;

  document.addEventListener('DOMContentLoaded', function () {
    var container = document.getElementById('hologram-canvas');
    if (!container || typeof THREE === 'undefined') {
      return;
    }

    buildScene(container);

    // Show the most recent bot reply (already server-rendered into the
    // chat history) as the initial caption, so it's not empty on load.
    var historyLines = document.querySelectorAll('#chat-window .chat-model .chat-text');
    if (historyLines.length) {
      setCaption(historyLines[historyLines.length - 1].textContent);
    }
  });
})();
