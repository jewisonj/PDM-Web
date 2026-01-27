const express = require('express');
const sqlite3 = require('sqlite3').verbose();
const path = require('path');
const fs = require('fs');

const app = express();
const PORT = 3000;

// Database path - configurable
const DB_PATH = process.env.PDM_DB_PATH || 'D:\\PDM_Vault\\pdm.sqlite';

// Serve static files from public directory
app.use(express.static('public'));

// API endpoint to get all items
app.get('/api/items', (req, res) => {
    const db = new sqlite3.Database(DB_PATH, sqlite3.OPEN_READONLY, (err) => {
        if (err) {
            console.error('Database connection error:', err);
            return res.status(500).json({ error: 'Database connection failed' });
        }
    });

    const query = `
        SELECT 
            item_number,
            name,
            description,
            revision,
            iteration,
            lifecycle_state,
            project,
            material,
            mass,
            thickness,
            cut_length,
            datetime(modified_at) as modified_at,
            datetime(created_at) as created_at
        FROM items
        ORDER BY modified_at DESC
    `;

    db.all(query, [], (err, rows) => {
        if (err) {
            console.error('Query error:', err);
            return res.status(500).json({ error: 'Query failed' });
        }
        res.json(rows);
    });

    db.close();
});

// API endpoint to get item details
app.get('/api/items/:itemNumber', (req, res) => {
    const itemNumber = req.params.itemNumber.toLowerCase();
    const db = new sqlite3.Database(DB_PATH, sqlite3.OPEN_READONLY, (err) => {
        if (err) {
            console.error('Database connection error:', err);
            return res.status(500).json({ error: 'Database connection failed' });
        }
    });

    // Get item info
    const itemQuery = `
        SELECT 
            item_number,
            name,
            description,
            revision,
            iteration,
            lifecycle_state,
            project,
            material,
            mass,
            thickness,
            cut_length,
            datetime(modified_at) as modified_at,
            datetime(created_at) as created_at
        FROM items
        WHERE item_number = ?
    `;

    db.get(itemQuery, [itemNumber], (err, item) => {
        if (err) {
            console.error('Item query error:', err);
            db.close();
            return res.status(500).json({ error: 'Query failed' });
        }

        if (!item) {
            db.close();
            return res.status(404).json({ error: 'Item not found' });
        }

        // Get all files for this item
        const filesQuery = `
            SELECT 
                file_id,
                file_path,
                file_type,
                revision,
                iteration,
                datetime(added_at) as added_at
            FROM files
            WHERE item_number = ?
            ORDER BY added_at DESC
        `;

        db.all(filesQuery, [itemNumber], (err, files) => {
            if (err) {
                console.error('Files query error:', err);
                db.close();
                return res.status(500).json({ error: 'Query failed' });
            }

            // Get BOM (where this item is parent)
            const bomParentQuery = `
                SELECT 
                    child_item,
                    quantity,
                    source_file,
                    datetime(created_at) as created_at
                FROM bom
                WHERE parent_item = ?
                ORDER BY child_item
            `;

            db.all(bomParentQuery, [itemNumber], (err, bomChildren) => {
                if (err) {
                    console.error('BOM query error:', err);
                    db.close();
                    return res.status(500).json({ error: 'Query failed' });
                }

                // Get where-used (where this item is child)
                const whereUsedQuery = `
                    SELECT 
                        parent_item,
                        quantity,
                        source_file,
                        datetime(created_at) as created_at
                    FROM bom
                    WHERE child_item = ?
                    ORDER BY parent_item
                `;

                db.all(whereUsedQuery, [itemNumber], (err, whereUsed) => {
                    if (err) {
                        console.error('Where-used query error:', err);
                        db.close();
                        return res.status(500).json({ error: 'Query failed' });
                    }

                    // Get lifecycle history
                    const historyQuery = `
                        SELECT 
                            old_state,
                            new_state,
                            old_revision,
                            new_revision,
                            old_iteration,
                            new_iteration,
                            changed_by,
                            datetime(changed_at) as changed_at
                        FROM lifecycle_history
                        WHERE item_number = ?
                        ORDER BY changed_at DESC
                    `;

                    db.all(historyQuery, [itemNumber], (err, history) => {
                        if (err) {
                            console.error('History query error:', err);
                            db.close();
                            return res.status(500).json({ error: 'Query failed' });
                        }

                        // Get checkout status
                        const checkoutQuery = `
                            SELECT 
                                username,
                                datetime(checked_out_at) as checked_out_at
                            FROM checkouts
                            WHERE item_number = ?
                        `;

                        db.get(checkoutQuery, [itemNumber], (err, checkout) => {
                            if (err) {
                                console.error('Checkout query error:', err);
                                db.close();
                                return res.status(500).json({ error: 'Query failed' });
                            }

                            db.close();

                            res.json({
                                item,
                                files,
                                bom: bomChildren,
                                whereUsed,
                                history,
                                checkout
                            });
                        });
                    });
                });
            });
        });
    });
});

// API endpoint to get file info by path (for opening files)
app.get('/api/files/info', (req, res) => {
    const filePath = req.query.path;
    
    if (!filePath) {
        return res.status(400).json({ error: 'File path required' });
    }

    // Check if file exists
    fs.access(filePath, fs.constants.F_OK, (err) => {
        if (err) {
            return res.json({ exists: false, path: filePath });
        }

        // Get file stats
        fs.stat(filePath, (err, stats) => {
            if (err) {
                return res.json({ exists: true, path: filePath, error: 'Could not read file stats' });
            }

            res.json({
                exists: true,
                path: filePath,
                size: stats.size,
                modified: stats.mtime,
                isDirectory: stats.isDirectory()
            });
        });
    });
});

// File serving endpoint - serve PDFs, SVGs, DXFs, etc.
app.get('/api/files/view', (req, res) => {
    const filePath = req.query.path;

    if (!filePath) {
        return res.status(400).send('File path required');
    }

    // Security check - ensure file is within PDM_Vault
    const vaultRoot = path.resolve('D:\\PDM_Vault');
    const requestedPath = path.resolve(filePath);

    if (!requestedPath.startsWith(vaultRoot)) {
        return res.status(403).send('Access denied - file outside vault');
    }

    // Check if file exists
    if (!fs.existsSync(filePath)) {
        return res.status(404).send('File not found');
    }

    // Determine content type
    const ext = path.extname(filePath).toLowerCase();
    const contentTypes = {
        '.pdf': 'application/pdf',
        '.svg': 'image/svg+xml',
        '.dxf': 'application/dxf',
        '.step': 'application/step',
        '.stp': 'application/step',
        '.png': 'image/png',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg'
    };

    const contentType = contentTypes[ext] || 'application/octet-stream';
    res.setHeader('Content-Type', contentType);

    // For PDFs and SVGs, set to display inline
    if (ext === '.pdf' || ext === '.svg') {
        res.setHeader('Content-Disposition', 'inline');
    }

    // Stream the file
    const fileStream = fs.createReadStream(filePath);
    fileStream.pipe(res);
});

// API endpoint to generate available part numbers
app.get('/api/available-numbers', (req, res) => {
    const db = new sqlite3.Database(DB_PATH, sqlite3.OPEN_READONLY, (err) => {
        if (err) {
            console.error('Database connection error:', err);
            return res.status(500).json({ error: 'Database connection failed' });
        }
    });

    // Query ALL items, filter in JavaScript for flexibility
    // Excludes supplier parts (spn, mmc) and test items (zzz)
    const query = `
        SELECT item_number 
        FROM items 
        ORDER BY item_number
    `;

    db.all(query, [], (err, rows) => {
        if (err) {
            console.error('Query error:', err);
            db.close();
            return res.status(500).json({ error: 'Query failed' });
        }

        // Prefixes to exclude
        const excludePrefixes = ['spn', 'mmc', 'zzz'];
        
        // Group by prefix (first 2 letters project + 1 letter type) and find highest number
        const prefixes = {};
        
        rows.forEach(row => {
            const itemNum = row.item_number.toLowerCase();
            
            // Match format: csp00100 (2 letter project + 1 letter type + digits)
            // Handles both 5 and 6 digit numbers
            const match = itemNum.match(/^([a-z]{2})([a-z])(\d{4,6})$/);
            if (match) {
                const project = match[1];  // cs, xx, wm, etc.
                const type = match[2];     // p, a
                const number = parseInt(match[3], 10);
                const prefix = (project + type).toUpperCase();  // CSP, CSA, XXP, WMP, etc.
                
                // Skip excluded prefixes
                if (excludePrefixes.includes(project + type)) {
                    return;
                }
                
                if (!prefixes[prefix] || number > prefixes[prefix]) {
                    prefixes[prefix] = number;
                }
            }
        });

        // Generate 50 available numbers for each prefix
        const result = {};
        Object.keys(prefixes).sort().forEach(prefix => {
            const highest = prefixes[prefix];
            const nextStart = highest + 10;
            const available = [];
            
            for (let i = 0; i < 50; i++) {
                available.push(nextStart + (i * 10));
            }
            
            result[prefix] = {
                highest: highest,
                next_start: nextStart,
                available: available
            };
        });

        db.close();
        res.json(result);
    });
});

// Health check endpoint
app.get('/api/health', (req, res) => {
    res.json({
        status: 'ok',
        dbPath: DB_PATH,
        timestamp: new Date().toISOString()
    });
});

// Serve the main page
app.get('/', (req, res) => {
    res.sendFile(path.join(__dirname, 'public', 'home.html'));
});

app.listen(PORT, () => {
    console.log(`PDM Browser Server running on http://localhost:${PORT}`);
    console.log(`Database: ${DB_PATH}`);
    console.log(`Press Ctrl+C to stop`);
});
