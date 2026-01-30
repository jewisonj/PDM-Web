# PDM System - Security Hardening Guide

**Production Security Implementation & Best Practices**
**Related Docs:** [README.md](README.md), [23-SYSTEM-CONFIGURATION.md](23-SYSTEM-CONFIGURATION.md), [21-BACKUP-RECOVERY-GUIDE.md](21-BACKUP-RECOVERY-GUIDE.md)

---

## 🔒 Security Levels

### **Level 1: Basic (Development/Testing)**
- Single-user local access only
- Default passwords acceptable
- No encryption required
- **Current Status:** v2.0 operates at this level

### **Level 2: Standard (Small Business)**
- Network access
- User authentication
- Database backups encrypted
- Audit logging
- **Target:** v3.0 support

### **Level 3: Enterprise (Large Organizations)**
- Multi-user authentication
- Role-based access control
- End-to-end encryption
- Comprehensive audit trails
- Compliance certifications
- **Target:** v4.0 support

---

## ✅ Current Security (v2.0)

**What's Secure:**
- ✅ Local file system access only
- ✅ No network exposure (default)
- ✅ Database on local drive
- ✅ Service account isolation (SYSTEM)

**What's Not Secure:**
- ❌ No user authentication
- ❌ No encryption at rest
- ❌ No network authentication
- ❌ Limited audit logging

**Recommendation:** v2.0 is suitable for single-user, local-only systems

---

## 🔐 Basic Security Hardening (Now)

### **1. File System Security**

**Restrict PDM Vault Access:**

```powershell
# Remove public access, keep only service account
$acl = Get-Acl "D:\PDM_Vault"

# Remove "Everyone" if present
$ace = $acl.Access | Where-Object {$_.IdentityReference -match "Everyone"}
if ($ace) {
    $acl.RemoveAccessRule($ace)
}

# Add SYSTEM (service account) with full access
$rule = New-Object System.Security.AccessControl.FileSystemAccessRule(
    "SYSTEM",
    "FullControl",
    "ContainerInherit,ObjectInherit",
    "None",
    "Allow"
)
$acl.AddAccessRule($rule)

# Add local admin with modify access
$rule2 = New-Object System.Security.AccessControl.FileSystemAccessRule(
    "BUILTIN\Administrators",
    "Modify",
    "ContainerInherit,ObjectInherit",
    "None",
    "Allow"
)
$acl.AddAccessRule($rule2)

Set-Acl "D:\PDM_Vault" $acl
Write-Host "Permissions updated"
```

### **2. Database Access**

**Backup Encryption:**

```powershell
# Encrypt backup files
function Encrypt-Backup {
    param([string]$BackupPath)

    # Use Windows EFS (Encrypting File System)
    cipher /e "$BackupPath"
    Write-Host "Backup encrypted: $BackupPath"
}

# Use when backing up
Encrypt-Backup "D:\PDM_Backups\2025-01-03"
```

### **3. Log File Security**

**Restrict Log Access:**

```powershell
# Only SYSTEM and Admins can read logs
$logFile = "D:\PDM_Vault\logs\pdm.log"
$acl = Get-Acl $logFile

# Remove public access
$acl.SetAccessRuleProtection($true, $false)

# Add SYSTEM and Admins only
$rules = @(
    [System.Security.AccessControl.FileSystemAccessRule]::new(
        "SYSTEM",
        "FullControl",
        "None",
        "None",
        "Allow"
    ),
    [System.Security.AccessControl.FileSystemAccessRule]::new(
        "BUILTIN\Administrators",
        "Modify",
        "None",
        "None",
        "Allow"
    )
)

foreach ($rule in $rules) {
    $acl.AddAccessRule($rule)
}

Set-Acl $logFile $acl
```

---

## 🔐 User Authentication (v3.0 Preparation)

### **Planned Multi-User Authentication**

When v3.0 adds multi-user support:

```powershell
# Users will authenticate with username/password
# Service will verify against user database
# Audit logs track who accessed what/when

# Session management:
# - Session timeout after 30 minutes
# - Automatic logout on browser close
# - Re-authentication for sensitive operations
```

### **Preparation Steps (Now)**

1. **Plan user structure**
   ```
   Admin Users:
   - Full system access
   - Can release items
   - Can delete items
   - Can manage users

   Power Users:
   - Can create/edit items
   - Can check in files
   - Can process BOMs
   - Cannot delete items
   - Cannot manage users

   View-Only Users:
   - Can view items
   - Can view BOMs
   - Can run reports
   - Cannot modify anything
   ```

2. **Plan database schema for users**
   ```sql
   CREATE TABLE users (
       user_id INTEGER PRIMARY KEY,
       username TEXT UNIQUE NOT NULL,
       password_hash TEXT NOT NULL,
       email TEXT,
       role TEXT,  -- admin, power_user, viewer
       created_at TEXT,
       last_login TEXT,
       active BOOLEAN DEFAULT 1
   );

   CREATE TABLE audit_log (
       log_id INTEGER PRIMARY KEY,
       user_id INTEGER NOT NULL,
       action TEXT NOT NULL,
       item_number TEXT,
       timestamp TEXT,
       FOREIGN KEY(user_id) REFERENCES users(user_id)
   );
   ```

3. **Plan password policy**
   - Minimum 12 characters
   - Uppercase + lowercase + numbers + special chars
   - 90-day expiration
   - Password history (no reuse of last 5)

---

## 🛡️ Network Security (If Exposing to Network)

### **Web Server Security**

**Do NOT expose PDM directly to internet without:**

```javascript
// 1. HTTPS/TLS encryption
const https = require('https');
const fs = require('fs');

const options = {
    key: fs.readFileSync('/path/to/key.pem'),
    cert: fs.readFileSync('/path/to/cert.pem')
};

https.createServer(options, app).listen(443);

// 2. Authentication middleware
app.use(requireAuth);

// 3. Rate limiting
const rateLimit = require('express-rate-limit');
const limiter = rateLimit({
    windowMs: 15 * 60 * 1000,  // 15 minutes
    max: 100  // limit each IP to 100 requests per windowMs
});
app.use(limiter);

// 4. CORS restrictions
const cors = require('cors');
app.use(cors({
    origin: ['https://yourdomain.com'],
    credentials: true
}));
```

### **API Security**

```javascript
// API Key validation
const apiKeyAuth = (req, res, next) => {
    const apiKey = req.headers['x-api-key'];
    const validKeys = process.env.API_KEYS.split(',');

    if (!apiKey || !validKeys.includes(apiKey)) {
        return res.status(401).json({ error: 'Invalid API key' });
    }

    next();
};

app.use('/api/', apiKeyAuth);
```

---

## 🔍 Audit & Compliance

### **Audit Logging**

```powershell
# Enhanced logging for compliance
function Write-AuditLog {
    param(
        [string]$Action,
        [string]$ItemNumber,
        [string]$User,
        [string]$Result
    )

    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $logEntry = "$timestamp | User: $User | Action: $Action | Item: $ItemNumber | Result: $Result"

    Add-Content "D:\PDM_Vault\logs\audit.log" $logEntry
}

# Usage
Write-AuditLog -Action "ItemCreated" -ItemNumber "csp0030" -User "admin" -Result "Success"
Write-AuditLog -Action "ItemReleased" -ItemNumber "csp0030" -User "admin" -Result "Success"
Write-AuditLog -Action "DataExport" -ItemNumber "All" -User "admin" -Result "Success"
```

### **Compliance Requirements**

**For regulated industries:**

- [ ] User authentication required
- [ ] Audit log for all changes
- [ ] Immutable backup copies
- [ ] Encryption of data at rest
- [ ] Encryption of data in transit
- [ ] Regular security audits
- [ ] Disaster recovery plan
- [ ] User access reviews
- [ ] Password policy enforcement
- [ ] Data retention policies

---

## 🚨 Security Incident Response

### **Compromised System Recovery**

**If system is compromised:**

1. **Immediate Actions:**
   ```powershell
   # 1. Stop all services
   Get-Service | Where-Object {$_.Name -like "PDM_*"} | Stop-Service

   # 2. Isolate network (if network-connected)
   # Disconnect cable or disable network

   # 3. Preserve evidence (don't clear logs)
   Copy-Item "D:\PDM_Vault" "D:\PDM_Vault.compromised_backup" -Recurse

   # 4. Notify stakeholders
   Write-Host "SECURITY INCIDENT: System compromised - contacting administrators"
   ```

2. **Assessment:**
   - Check access logs for unauthorized access
   - Review recent file modifications
   - Check for data exfiltration
   - Verify database integrity

3. **Recovery:**
   - Restore from known-good backup
   - Change all passwords
   - Update access controls
   - Re-test all services
   - Document incident

---

## 🔑 Key Management

### **API Keys & Secrets**

**Never hardcode secrets!**

```powershell
# BAD - Don't do this
$apiKey = "abc123def456"

# GOOD - Use environment variables
$apiKey = $env:PDM_API_KEY

# BETTER - Use secure vaults
# (PowerShell Credential Manager, Azure Key Vault, etc.)
```

**Set environment variable:**
```powershell
# One-time (current session)
$env:PDM_API_KEY = "your-secret-key"

# Permanently (requires admin)
[Environment]::SetEnvironmentVariable("PDM_API_KEY", "your-secret-key", "Machine")
```

---

## ✓ Security Checklist

### **Basic Security (Do Now)**
- [ ] Restrict PDM_Vault NTFS permissions
- [ ] Restrict log file access
- [ ] Enable database backups
- [ ] Encrypt backup storage
- [ ] Document access procedures
- [ ] Create incident response plan

### **Standard Security (v3.0)**
- [ ] User authentication system
- [ ] Audit logging for all changes
- [ ] Role-based access control
- [ ] Session management
- [ ] Password policy enforcement
- [ ] Regular security audits

### **Enterprise Security (v4.0)**
- [ ] Encryption at rest (database)
- [ ] Encryption in transit (TLS)
- [ ] Advanced threat detection
- [ ] Compliance certifications
- [ ] Penetration testing
- [ ] Security operations center

---

## 📋 Security Documentation

**Document these items:**
- [ ] Access procedures
- [ ] Password reset process
- [ ] Data backup procedures
- [ ] Disaster recovery plan
- [ ] Incident response plan
- [ ] Security policies
- [ ] Audit procedures
- [ ] Compliance requirements

---

## 🔗 Security Resources

- **OWASP Top 10:** https://owasp.org/www-project-top-ten/
- **Windows Security:** https://docs.microsoft.com/en-us/windows/security/
- **PowerShell Security:** https://learn.microsoft.com/powershell/scripting/learn/security/
- **SQLite Security:** https://www.sqlite.org/security.html
- **Express.js Security:** https://expressjs.com/en/advanced/best-practice-security.html

---

**Last Updated:** 2025-01-03
**Version:** 2.0
**Security Level:** Basic (Development-Safe)
**Next Review:** When implementing multi-user features
**Related:** [23-SYSTEM-CONFIGURATION.md](23-SYSTEM-CONFIGURATION.md), [21-BACKUP-RECOVERY-GUIDE.md](21-BACKUP-RECOVERY-GUIDE.md)
