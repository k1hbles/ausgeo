-- Small real-world fixture so the search layer can be validated before the
-- full 15.9M-row load finishes. Coordinates are approximate but real places.
INSERT INTO address
  (gnaf_pid, unit, number, number_int, street, locality, state, postcode, lat, lon, reliability, search_text)
VALUES
  -- Wattle St Newtown: several numbers on one street
  ('FIX0001', NULL, '40',    40, 'WATTLE ST',     'NEWTOWN',        'NSW', '2042', -33.8961, 151.1791, 2, 'WATTLE ST NEWTOWN'),
  ('FIX0002', NULL, '42',    42, 'WATTLE ST',     'NEWTOWN',        'NSW', '2042', -33.8965, 151.1795, 2, 'WATTLE ST NEWTOWN'),
  ('FIX0003', '3',  '42',    42, 'WATTLE ST',     'NEWTOWN',        'NSW', '2042', -33.8965, 151.1795, 2, 'WATTLE ST NEWTOWN'),
  ('FIX0004', '7',  '42',    42, 'WATTLE ST',     'NEWTOWN',        'NSW', '2042', -33.8965, 151.1795, 2, 'WATTLE ST NEWTOWN'),
  ('FIX0005', NULL, '44',    44, 'WATTLE ST',     'NEWTOWN',        'NSW', '2042', -33.8969, 151.1799, 2, 'WATTLE ST NEWTOWN'),
  -- same street name, different suburb: locality must disambiguate
  ('FIX0006', NULL, '42',    42, 'WATTLE ST',     'ULTIMO',         'NSW', '2007', -33.8790, 151.1980, 2, 'WATTLE ST ULTIMO'),
  ('FIX0007', NULL, '42',    42, 'WATTLE STREET', 'PUNCHBOWL',      'NSW', '2196', -33.9280, 151.0550, 2, 'WATTLE STREET PUNCHBOWL'),
  -- CBD
  ('FIX0008', NULL, '100',  100, 'GEORGE ST',     'SYDNEY',         'NSW', '2000', -33.8620, 151.2070, 1, 'GEORGE ST SYDNEY'),
  ('FIX0009', '2',  '100',  100, 'GEORGE ST',     'SYDNEY',         'NSW', '2000', -33.8620, 151.2070, 1, 'GEORGE ST SYDNEY'),
  ('FIX0010', NULL, '200',  200, 'GEORGE ST',     'SYDNEY',         'NSW', '2000', -33.8650, 151.2080, 1, 'GEORGE ST SYDNEY'),
  -- interstate
  ('FIX0011', NULL, '100-102', 100, 'COLLINS ST', 'MELBOURNE',      'VIC', '3000', -37.8150, 144.9660, 1, 'COLLINS ST MELBOURNE'),
  ('FIX0012', NULL, '10',    10, 'SMITH RD',      'RICHMOND',       'VIC', '3121', -37.8183, 145.0000, 2, 'SMITH RD RICHMOND'),
  ('FIX0013', '5',  '10-12', 10, 'SMITH RD',      'RICHMOND',       'VIC', '3121', -37.8183, 145.0000, 2, 'SMITH RD RICHMOND'),
  ('FIX0014', NULL, '5',      5, 'HAY STREET',    'PERTH',          'WA',  '6000', -31.9530, 115.8590, 2, 'HAY STREET PERTH'),
  ('FIX0015', '12', '5',      5, 'HAY STREET',    'PERTH',          'WA',  '6000', -31.9530, 115.8590, 2, 'HAY STREET PERTH'),
  ('FIX0016', NULL, '9',      9, 'ELDER ST',      'ADELAIDE',       'SA',  '5000', -34.9280, 138.5990, 2, 'ELDER ST ADELAIDE'),
  ('FIX0017', NULL, '7B',     7, 'SHORT ST',      'HOBART',         'TAS', '7000', -42.8820, 147.3270, 2, 'SHORT ST HOBART'),
  ('FIX0018', NULL, '1',      1, 'QUEEN ST',      'BRISBANE',       'QLD', '4000', -27.4700, 153.0250, 1, 'QUEEN ST BRISBANE'),
  ('FIX0019', NULL, '2042',2042, 'PACIFIC HWY',   'LINDFIELD',      'NSW', '2070', -33.7770, 151.1690, 2, 'PACIFIC HWY LINDFIELD'),
  ('FIX0020', NULL, '14',    14, 'L ESTRANGE ST', 'GLENELG',        'SA',  '5045', -34.9800, 138.5140, 2, 'L ESTRANGE ST GLENELG');
