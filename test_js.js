const fs = require('fs');
const content = fs.readFileSync('templates/patient_profile.html', 'utf8');
const scriptRegex = /<script\b[^>]*>([\s\S]*?)<\/script>/gi;
let match;
let count = 0;
while ((match = scriptRegex.exec(content)) !== null) {
    count++;
    try {
        new Function(match[1]); // This checks for syntax errors!
    } catch (e) {
        console.error(`Syntax error in script block ${count}:\n`, e.message);
    }
}
console.log("Checked " + count + " script blocks.");
