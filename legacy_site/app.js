const DEFAULT_RANGE_KM = 25;
const AUTH_CONFIG_PATH = 'auth/config.yaml';
const EARTH_RADIUS_METERS = 6371008.8;
const WEB_MERCATOR = 'EPSG:3857';
const WGS84 = 'EPSG:4326';

const map = L.map('map', {
  boxZoom: false,
  zoomControl: false,
}).setView([-15.8, -47.9], 5);

L.control.zoom({ position: 'bottomright' }).addTo(map);

L.tileLayer(
  'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
  {
    maxZoom: 19,
    attribution:
      'Tiles &copy; Esri, Maxar, Earthstar Geographics, and the GIS User Community',
  }
).addTo(map);

const farmLayer = L.geoJSON(null, {
  style: getFarmStyle,
  onEachFeature(feature, layer) {
    const props = feature.properties || {};
    const label =
      props.nome || props.NOME || props.Name || props.NAME || props.fazenda || props.FAZENDA;
    if (label) {
      layer.bindTooltip(String(label), { sticky: true });
    }
  },
}).addTo(map);

const sightLayer = L.layerGroup().addTo(map);
const intersectionLayer = L.layerGroup().addTo(map);
const previewLayer = L.layerGroup().addTo(map);

const towerRows = document.querySelector('#towerRows');
const towerTemplate = document.querySelector('#towerTemplate');
const towerForm = document.querySelector('#towerForm');
const addTowerButton = document.querySelector('#addTower');
const rangeKmInput = document.querySelector('#rangeKm');
const rangeSummary = document.querySelector('#rangeSummary');
const intersectionCount = document.querySelector('#intersectionCount');
const loadStatus = document.querySelector('#loadStatus');
const loadDot = document.querySelector('#loadDot');
const authScreen = document.querySelector('#authScreen');
const loginForm = document.querySelector('#loginForm');
const loginUser = document.querySelector('#loginUser');
const loginPassword = document.querySelector('#loginPassword');
const authMessage = document.querySelector('#authMessage');
const logoutButton = document.querySelector('#logoutButton');
const tabButtons = [...document.querySelectorAll('.tab-button')];
const tabPanels = [...document.querySelectorAll('.tab-panel')];
const companyList = document.querySelector('#companyList');
const applyCompanies = document.querySelector('#applyCompanies');
let lastMapLatLng = null;
let isPointerOverMap = false;
let pendingCoordinateMarker = null;
let selectedTowerIndex = null;
let authConfig = null;
let allFarmGeojson = null;
let selectedCompanies = new Set();

document.body.classList.add('is-locked');

function setStatus(message, state = 'loading') {
  loadStatus.textContent = message;
  loadDot.className = `status-dot ${state}`;
}

function getFeatureCompany(feature) {
  const props = feature?.properties || {};
  return String(props.EMPRESA || props.empresa || props.GEL || props.gel || 'Sem empresa').trim();
}

function getFarmStyle(feature) {
  const company = getFeatureCompany(feature);
  const hasSelection = selectedCompanies.size > 0;
  const isSelected = selectedCompanies.has(company);

  return {
    color: isSelected ? '#ffcf4a' : '#267a58',
    weight: isSelected ? 2.4 : 1.4,
    opacity: hasSelection && !isSelected ? 0.35 : 0.9,
    fillColor: isSelected ? '#ffcf4a' : '#58a77d',
    fillOpacity: hasSelection && !isSelected ? 0.08 : 0.22,
  };
}

function setActiveTab(tabId) {
  tabButtons.forEach((button) => {
    button.classList.toggle('is-active', button.dataset.tab === tabId);
  });
  tabPanels.forEach((panel) => {
    const isActive = panel.id === tabId;
    panel.classList.toggle('is-active', isActive);
    panel.hidden = !isActive;
  });
  map.invalidateSize();
}

function getSelectedCompanyNames() {
  return [...companyList.querySelectorAll('input[type="checkbox"]:checked')].map(
    (input) => input.value
  );
}

function renderCompanyList(geojson) {
  const companies = [
    ...new Set((geojson.features || []).map(getFeatureCompany).filter(Boolean)),
  ].sort((a, b) => a.localeCompare(b, 'pt-BR'));

  if (!companies.length) {
    companyList.innerHTML = '<p class="muted-text">Nenhuma empresa encontrada no campo EMPRESA.</p>';
    return;
  }

  companyList.innerHTML = '';
  companies.forEach((company) => {
    const label = document.createElement('label');
    label.className = 'company-option';

    const input = document.createElement('input');
    input.type = 'checkbox';
    input.value = company;

    const text = document.createElement('span');
    text.textContent = company;

    label.append(input, text);
    companyList.append(label);
  });
}

function applyCompanySelection() {
  if (!allFarmGeojson) {
    return;
  }

  selectedCompanies = new Set(getSelectedCompanyNames());
  farmLayer.setStyle(getFarmStyle);

  if (!selectedCompanies.size) {
    const bounds = farmLayer.getBounds();
    if (bounds.isValid()) {
      map.fitBounds(bounds.pad(0.08));
    }
    setStatus('Todas as empresas estão visíveis.', 'ready');
    return;
  }

  const selectedLayer = L.geoJSON({
    type: 'FeatureCollection',
    features: allFarmGeojson.features.filter((feature) => selectedCompanies.has(getFeatureCompany(feature))),
  });
  const bounds = selectedLayer.getBounds();
  if (bounds.isValid()) {
    map.fitBounds(bounds.pad(0.12));
  }
  setStatus(`${selectedCompanies.size} empresa(s) aplicada(s) ao projeto.`, 'ready');
}

function setAuthMessage(message, state = 'neutral') {
  authMessage.textContent = message;
  authMessage.dataset.state = state;
}

function getBcrypt() {
  return window.dcodeIO?.bcrypt || window.bcrypt;
}

async function verifyPassword(password, hash) {
  const bcrypt = getBcrypt();
  if (!bcrypt) {
    throw new Error('Biblioteca bcrypt não foi carregada.');
  }

  const normalizedHash = String(hash).replace(/^\$2y\$/, '$2b$');
  if (typeof bcrypt.compareSync === 'function') {
    return bcrypt.compareSync(password, normalizedHash);
  }

  return bcrypt.compare(password, normalizedHash);
}

async function loadAuthConfig() {
  if (authConfig) {
    return authConfig;
  }

  if (!window.jsyaml) {
    throw new Error('Biblioteca js-yaml não foi carregada.');
  }

  const response = await fetch(`${AUTH_CONFIG_PATH}?v=${Date.now()}`, { cache: 'no-store' });
  if (!response.ok) {
    throw new Error(`${AUTH_CONFIG_PATH} não foi encontrado.`);
  }

  const text = await response.text();
  authConfig = window.jsyaml.load(text);
  return authConfig;
}

function openSession(username, profile) {
  sessionStorage.setItem(
    'fireModelAuth',
    JSON.stringify({
      username,
      name: profile.name || username,
      role: profile.role || 'user',
    })
  );
  document.body.classList.remove('is-locked');
  authScreen.hidden = true;
  map.invalidateSize();
  setStatus(`Acesso liberado para ${profile.name || username}.`, 'ready');
}

function restoreSession() {
  const session = sessionStorage.getItem('fireModelAuth');
  if (!session) {
    loginUser.focus();
    return;
  }

  try {
    const profile = JSON.parse(session);
    document.body.classList.remove('is-locked');
    authScreen.hidden = true;
    map.invalidateSize();
    setStatus(`Acesso liberado para ${profile.name || profile.username}.`, 'ready');
  } catch {
    sessionStorage.removeItem('fireModelAuth');
    loginUser.focus();
  }
}

async function authenticate(username, password) {
  const config = await loadAuthConfig();
  const normalizedUsername = username.trim().toLowerCase();
  const users = config?.credentials?.usernames || {};
  const matchedKey = Object.keys(users).find((key) => key.toLowerCase() === normalizedUsername);
  const profile = matchedKey ? users[matchedKey] : null;
  if (!profile?.password) {
    return null;
  }

  const isValid = await verifyPassword(password, profile.password);
  return isValid ? { username: matchedKey, profile } : null;
}

function addTowerRow(values = {}) {
  const fragment = towerTemplate.content.cloneNode(true);
  const row = fragment.querySelector('.tower-row');
  row.querySelector('[name="x"]').value = values.x ?? '';
  row.querySelector('[name="y"]').value = values.y ?? '';
  row.querySelector('[name="angle"]').value = values.angle ?? '0';
  row.querySelector('.remove-tower').addEventListener('click', () => {
    if (towerRows.querySelectorAll('.tower-row').length === 1) {
      selectedTowerIndex = null;
      map.dragging.enable();
      row.querySelector('[name="x"]').value = '';
      row.querySelector('[name="y"]').value = '';
      row.querySelector('[name="angle"]').value = '0';
      sightLayer.clearLayers();
      intersectionLayer.clearLayers();
      intersectionCount.textContent = '0';
      clearPendingCoordinate();
      row.querySelector('[name="x"]').focus();
      setStatus('Dados do ponto limpos.', 'ready');
      return;
    }

    selectedTowerIndex = null;
    map.dragging.enable();
    row.remove();
    refreshRowTitles();
    renderSightLines({ validate: false });
  });
  towerRows.append(row);
  refreshRowTitles();
}

function refreshRowTitles() {
  const rows = [...towerRows.querySelectorAll('.tower-row')];
  rows.forEach((row, index) => {
    row.querySelector('.tower-name').textContent = `Ponto ${index + 1}`;
    row.classList.toggle('is-selected', index === selectedTowerIndex);
  });
}

function readTowers() {
  return [...towerRows.querySelectorAll('.tower-row')].map((row, index) => {
    const x = Number(row.querySelector('[name="x"]').value);
    const y = Number(row.querySelector('[name="y"]').value);
    const angle = Number(row.querySelector('[name="angle"]').value);
    return { index, x, y, angle };
  });
}

function getRangeKm() {
  const value = Number(rangeKmInput.value);
  return Number.isFinite(value) && value > 0 ? value : DEFAULT_RANGE_KM;
}

function getRangeMeters() {
  return getRangeKm() * 1000;
}

function updateRangeSummary() {
  rangeSummary.textContent = `${getRangeKm().toLocaleString('pt-BR', {
    maximumFractionDigits: 2,
  })} km`;
}

function degreesToRadians(value) {
  return (value * Math.PI) / 180;
}

function radiansToDegrees(value) {
  return (value * 180) / Math.PI;
}

function normalizeLongitude(value) {
  return ((value + 540) % 360) - 180;
}

function normalizeAngle(value) {
  return ((value % 360) + 360) % 360;
}

function lngLatToMapPoint(lng, lat) {
  const [x, y] = proj4(WGS84, WEB_MERCATOR, [lng, lat]);
  return { x, y };
}

function mapPointToLatLng(point) {
  const [lng, lat] = proj4(WEB_MERCATOR, WGS84, [point.x, point.y]);
  return L.latLng(lat, lng);
}

function getBearingDegrees(startLatLng, endLatLng) {
  const startLat = degreesToRadians(startLatLng.lat);
  const endLat = degreesToRadians(endLatLng.lat);
  const deltaLng = degreesToRadians(endLatLng.lng - startLatLng.lng);
  const y = Math.sin(deltaLng) * Math.cos(endLat);
  const x =
    Math.cos(startLat) * Math.sin(endLat) -
    Math.sin(startLat) * Math.cos(endLat) * Math.cos(deltaLng);
  return normalizeAngle(radiansToDegrees(Math.atan2(y, x)));
}

function getPointToSegmentDistance(point, start, end) {
  const dx = end.x - start.x;
  const dy = end.y - start.y;

  if (dx === 0 && dy === 0) {
    return point.distanceTo(start);
  }

  const ratio = Math.max(
    0,
    Math.min(1, ((point.x - start.x) * dx + (point.y - start.y) * dy) / (dx * dx + dy * dy))
  );
  const projection = L.point(start.x + ratio * dx, start.y + ratio * dy);
  return point.distanceTo(projection);
}

function findNearestSightLine(latLng) {
  const towers = readTowers();
  let nearest = null;
  let nearestDistance = Infinity;
  const clickPoint = map.latLngToContainerPoint(latLng);

  towers.forEach((tower) => {
    const segment = makeSightSegment(tower);
    const start = map.latLngToContainerPoint(segment.startLatLng);
    const end = map.latLngToContainerPoint(segment.endLatLng);
    const distance = getPointToSegmentDistance(clickPoint, start, end);

    if (distance < nearestDistance) {
      nearestDistance = distance;
      nearest = tower.index;
    }
  });

  return nearestDistance <= 18 ? nearest : null;
}

function selectNearestSightLine(latLng) {
  if (!towerForm.checkValidity()) {
    return;
  }

  const towerIndex = findNearestSightLine(latLng);
  if (towerIndex === null) {
    clearSelectedSightLine();
    setStatus('Use Shift+clique sobre ou perto de uma linha para rotacionar.', 'error');
    return;
  }

  selectSightLine(towerIndex);
}

function findNextEmptyTowerRow() {
  return [...towerRows.querySelectorAll('.tower-row')].find((row) => {
    const xInput = row.querySelector('[name="x"]');
    const yInput = row.querySelector('[name="y"]');
    return !xInput.value || !yInput.value;
  });
}

function clearPendingCoordinate() {
  previewLayer.clearLayers();
  pendingCoordinateMarker = null;
  map.closePopup();
}

function makeCoordinatePopup(latLng) {
  const popup = document.createElement('div');
  popup.className = 'coordinate-popup';

  const title = document.createElement('strong');
  title.textContent = 'Usar esta coordenada?';

  const coordinate = document.createElement('p');
  coordinate.textContent = `${latLng.lng.toFixed(6)}, ${latLng.lat.toFixed(6)}`;

  const actions = document.createElement('div');
  actions.className = 'coordinate-popup-actions';

  const acceptButton = document.createElement('button');
  acceptButton.type = 'button';
  acceptButton.className = 'popup-accept';
  acceptButton.textContent = 'Aceitar';
  acceptButton.addEventListener('click', () => fillNextTowerFromMap(latLng));

  const cancelButton = document.createElement('button');
  cancelButton.type = 'button';
  cancelButton.className = 'popup-cancel';
  cancelButton.textContent = 'Cancelar';
  cancelButton.addEventListener('click', clearPendingCoordinate);

  actions.append(acceptButton, cancelButton);
  popup.append(title, coordinate, actions);
  return popup;
}

function previewCoordinate(latLng) {
  if (!latLng) {
    setStatus('Passe o mouse sobre o mapa antes de capturar a coordenada.', 'error');
    return;
  }

  clearPendingCoordinate();
  pendingCoordinateMarker = L.circleMarker(latLng, {
    radius: 8,
    color: '#ffffff',
    weight: 3,
    fillColor: '#c98216',
    fillOpacity: 1,
  }).addTo(previewLayer);

  pendingCoordinateMarker
    .bindPopup(makeCoordinatePopup(latLng), {
      closeButton: false,
      autoClose: false,
      closeOnClick: false,
      className: 'coordinate-leaflet-popup',
    })
    .openPopup();

  setStatus('Confirme a coordenada no pop-up do mapa.', 'ready');
}

function fillNextTowerFromMap(latLng) {
  if (!latLng) {
    setStatus('Passe o mouse sobre o mapa antes de capturar a coordenada.', 'error');
    return;
  }

  let row = findNextEmptyTowerRow();
  if (!row) {
    addTowerRow();
    row = towerRows.querySelector('.tower-row:last-child');
  }

  row.querySelector('[name="x"]').value = latLng.lng.toFixed(6);
  row.querySelector('[name="y"]').value = latLng.lat.toFixed(6);
  row.querySelector('[name="angle"]').value = '0';
  clearPendingCoordinate();
  setStatus('Coordenada aceita com ângulo inicial de 0°.', 'ready');
  renderSightLines({ validate: false });
}

function clearSelectedSightLine() {
  if (selectedTowerIndex === null) {
    return;
  }

  selectedTowerIndex = null;
  map.dragging.enable();
  map.getContainer().classList.remove('is-rotating-line');
  refreshRowTitles();
  renderSightLines({ validate: false, fit: false });
  setStatus('Rotação da linha encerrada.', 'ready');
}

function selectSightLine(towerIndex) {
  selectedTowerIndex = towerIndex;
  map.dragging.disable();
  map.getContainer().classList.add('is-rotating-line');
  refreshRowTitles();
  renderSightLines({ validate: false, fit: false });
  setStatus('Linha selecionada. Mova o mouse no mapa para rotacionar.', 'ready');
}

function rotateSelectedSightLine(latLng) {
  if (selectedTowerIndex === null || pendingCoordinateMarker) {
    return;
  }

  const row = [...towerRows.querySelectorAll('.tower-row')][selectedTowerIndex];
  if (!row) {
    selectedTowerIndex = null;
    map.dragging.enable();
    map.getContainer().classList.remove('is-rotating-line');
    return;
  }

  const lng = Number(row.querySelector('[name="x"]').value);
  const lat = Number(row.querySelector('[name="y"]').value);
  if (!Number.isFinite(lng) || !Number.isFinite(lat)) {
    return;
  }

  const angle = getBearingDegrees(L.latLng(lat, lng), latLng);
  row.querySelector('[name="angle"]').value = angle.toFixed(2);
  renderSightLines({ validate: false, fit: false });
}

function getEndpoint(tower) {
  const bearing = degreesToRadians(tower.angle);
  const distance = getRangeMeters() / EARTH_RADIUS_METERS;
  const startLat = degreesToRadians(tower.y);
  const startLng = degreesToRadians(tower.x);
  const endLat = Math.asin(
    Math.sin(startLat) * Math.cos(distance) +
      Math.cos(startLat) * Math.sin(distance) * Math.cos(bearing)
  );
  const endLng =
    startLng +
    Math.atan2(
      Math.sin(bearing) * Math.sin(distance) * Math.cos(startLat),
      Math.cos(distance) - Math.sin(startLat) * Math.sin(endLat)
    );

  return {
    x: normalizeLongitude(radiansToDegrees(endLng)),
    y: radiansToDegrees(endLat),
  };
}

function makeSightSegment(tower) {
  const end = getEndpoint(tower);
  const startLatLng = L.latLng(tower.y, tower.x);
  const endLatLng = L.latLng(end.y, end.x);
  return {
    tower,
    start: lngLatToMapPoint(tower.x, tower.y),
    end: lngLatToMapPoint(end.x, end.y),
    startLatLng,
    endLatLng,
  };
}

function findSegmentIntersection(a, b) {
  const x1 = a.start.x;
  const y1 = a.start.y;
  const x2 = a.end.x;
  const y2 = a.end.y;
  const x3 = b.start.x;
  const y3 = b.start.y;
  const x4 = b.end.x;
  const y4 = b.end.y;
  const denominator = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4);

  if (Math.abs(denominator) < 0.000001) {
    return null;
  }

  const t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denominator;
  const u = -((x1 - x2) * (y1 - y3) - (y1 - y2) * (x1 - x3)) / denominator;

  if (t < 0 || t > 1 || u < 0 || u > 1) {
    return null;
  }

  return {
    x: x1 + t * (x2 - x1),
    y: y1 + t * (y2 - y1),
  };
}

function renderSightLines({ validate = true, fit = true } = {}) {
  updateRangeSummary();

  if (validate && !towerForm.reportValidity()) {
    return;
  }

  if (!validate && !towerForm.checkValidity()) {
    return;
  }

  sightLayer.clearLayers();
  intersectionLayer.clearLayers();

  const segments = readTowers().map(makeSightSegment);
  const bounds = L.latLngBounds([]);

  segments.forEach((segment) => {
    const isSelected = segment.tower.index === selectedTowerIndex;
    const line = L.polyline([segment.startLatLng, segment.endLatLng], {
      color: isSelected ? '#ffcf4a' : '#c98216',
      weight: isSelected ? 6 : 3,
      opacity: 0.95,
    }).bindTooltip(
      `Ponto ${segment.tower.index + 1}: ${segment.tower.angle.toFixed(2)}° / ${getRangeKm().toLocaleString('pt-BR', { maximumFractionDigits: 2 })} km`
    );

    const hitLine = L.polyline([segment.startLatLng, segment.endLatLng], {
      color: '#ffffff',
      weight: 18,
      opacity: 0.001,
    });

    const handleLineSelection = (event) => {
      if (event.originalEvent.shiftKey) {
        L.DomEvent.stop(event.originalEvent);
        selectSightLine(segment.tower.index);
        return;
      }

      clearSelectedSightLine();
    };

    line.on('click', handleLineSelection);
    hitLine.on('click', handleLineSelection);

    const marker = L.circleMarker(segment.startLatLng, {
      radius: isSelected ? 8 : 6,
      color: '#ffffff',
      weight: 2,
      fillColor: isSelected ? '#ffcf4a' : '#0b7189',
      fillOpacity: 1,
    }).bindTooltip(`Ponto ${segment.tower.index + 1}`, { permanent: false });

    sightLayer.addLayer(hitLine);
    sightLayer.addLayer(line);
    sightLayer.addLayer(marker);
    bounds.extend(segment.startLatLng);
    bounds.extend(segment.endLatLng);
  });

  const intersections = [];
  for (let i = 0; i < segments.length; i += 1) {
    for (let j = i + 1; j < segments.length; j += 1) {
      const point = findSegmentIntersection(segments[i], segments[j]);
      if (point) {
        intersections.push(point);
      }
    }
  }

  intersections.forEach((point, index) => {
    const latLng = mapPointToLatLng(point);
    L.circleMarker(latLng, {
      radius: 7,
      color: '#ffffff',
      weight: 2,
      fillColor: '#bd3d34',
      fillOpacity: 1,
    })
      .bindTooltip(`Cruzamento ${index + 1}`)
      .addTo(intersectionLayer);
    bounds.extend(latLng);
  });

  intersectionCount.textContent = String(intersections.length);

  if (fit && bounds.isValid()) {
    map.fitBounds(bounds.pad(0.35), { maxZoom: 14 });
  }
}

async function loadFarms() {
  try {
    const geojson = await shp('data/Geo.zip');
    allFarmGeojson = geojson;
    farmLayer.addData(geojson);
    renderCompanyList(geojson);
    const bounds = farmLayer.getBounds();
    if (bounds.isValid()) {
      map.fitBounds(bounds.pad(0.08));
    }
    setStatus('Mapa das fazendas carregado.', 'ready');
  } catch (error) {
    console.error(error);
    setStatus('Não foi possível carregar data/Geo.zip.', 'error');
  }
}

addTowerButton.addEventListener('click', () => addTowerRow());
tabButtons.forEach((button) => {
  button.addEventListener('click', () => setActiveTab(button.dataset.tab));
});
applyCompanies.addEventListener('click', applyCompanySelection);
loginForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const username = loginUser.value.trim();
  const password = loginPassword.value;

  if (!username || !password) {
    setAuthMessage('Informe usuário e senha.', 'error');
    return;
  }

  loginForm.querySelector('button[type="submit"]').disabled = true;
  setAuthMessage('Validando credenciais...', 'neutral');

  try {
    const authResult = await authenticate(username, password);
    if (!authResult) {
      setAuthMessage('Usuário ou senha inválidos.', 'error');
      loginPassword.value = '';
      loginPassword.focus();
      return;
    }

    loginPassword.value = '';
    openSession(authResult.username, authResult.profile);
  } catch (error) {
    console.error(error);
    setAuthMessage(error.message || 'Não foi possível carregar a configuração de autenticação.', 'error');
  } finally {
    loginForm.querySelector('button[type="submit"]').disabled = false;
  }
});
logoutButton.addEventListener('click', () => {
  sessionStorage.removeItem('fireModelAuth');
  document.body.classList.add('is-locked');
  authScreen.hidden = false;
  loginPassword.value = '';
  loginUser.focus();
  setAuthMessage('Sessão encerrada.', 'neutral');
});
rangeKmInput.addEventListener('input', () => {
  updateRangeSummary();
  renderSightLines({ validate: false, fit: false });
});
map.on('mousemove', (event) => {
  lastMapLatLng = event.latlng;
  rotateSelectedSightLine(event.latlng);
});
map.on('mouseover', () => {
  isPointerOverMap = true;
});
map.on('mouseout', () => {
  isPointerOverMap = false;
});
map.on('click', (event) => {
  if (event.originalEvent.ctrlKey) {
    event.originalEvent.preventDefault();
    previewCoordinate(event.latlng);
    return;
  }

  if (event.originalEvent.shiftKey) {
    event.originalEvent.preventDefault();
    selectNearestSightLine(event.latlng);
    return;
  }

  clearSelectedSightLine();
});
map.on('mousedown', (event) => {
  if (event.originalEvent.shiftKey || selectedTowerIndex !== null) {
    event.originalEvent.preventDefault();
  }
});
document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape') {
    clearSelectedSightLine();
  }
});
document.addEventListener('keydown', (event) => {
  if (event.key === 'Control' && !event.repeat && isPointerOverMap) {
    event.preventDefault();
    previewCoordinate(lastMapLatLng);
  }
});
towerForm.addEventListener('submit', (event) => {
  event.preventDefault();
  renderSightLines();
});

addTowerRow();
updateRangeSummary();
loadFarms();
restoreSession();
