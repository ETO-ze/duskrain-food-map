import test from 'node:test';
import assert from 'node:assert/strict';
import { containsPosition, distanceKm, matchesSearch, nearbyPlaces, sameBounds } from '../src/utils/explore.js';

test('Search supports multiple terms, case and incomplete input', () => {
  const place = { name: 'MIO 洋房菜', city: '哈尔滨', address: '花园街' };
  assert.equal(matchesSearch(place, 'mio 哈尔滨'), true);
  assert.equal(matchesSearch(place, '天津'), false);
  assert.equal(matchesSearch(place, '   '), true);
});
test('Viewport handles boundaries and the international date line', () => {
  assert.equal(containsPosition({ minLng: 170, maxLng: -170, minLat: -10, maxLat: 10 }, { lng: 179, lat: 0 }), true);
  assert.equal(containsPosition({ minLng: 170, maxLng: -170, minLat: -10, maxLat: 10 }, { lng: 0, lat: 0 }), false);
  assert.equal(containsPosition(null, { lng: 0, lat: 0 }), true);
});
test('Nearby never falls back to distant stores and supports explicit expansion', () => {
  const stores = [{ id: 1, lng: 0.5, lat: 0 }, { id: 2, lng: 10, lat: 0 }];
  assert.equal(nearbyPlaces(stores, { lng: 0, lat: 0 }, 30, (p) => p).length, 0);
  assert.deepEqual(nearbyPlaces(stores, { lng: 0, lat: 0 }, 100, (p) => p).map((p) => p.id), [1]);
  assert.equal(stores[0].distanceKm, undefined);
});
test('Distance and viewport comparison are numerically stable', () => {
  assert.equal(distanceKm({ lng: 0, lat: 0 }, { lng: 0, lat: 0 }), 0);
  assert.ok(Math.abs(distanceKm({ lng: 0, lat: 0 }, { lng: 1, lat: 0 }) - 111.195) < 0.01);
  assert.equal(sameBounds(null, {}), false);
  const bounds = { minLng: 1, maxLng: 2, minLat: 3, maxLat: 4 };
  assert.equal(sameBounds(bounds, { ...bounds }), true);
  assert.equal(sameBounds(bounds, { ...bounds, minLng: 1.1 }), false);
});
