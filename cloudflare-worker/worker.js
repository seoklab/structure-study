/**
 * Cloudflare Worker for Protein Competition Submissions
 *
 * This worker receives form submissions and creates GitHub Issues
 * via the GitHub API, allowing users to submit without a GitHub account.
 *
 * Environment variables required (set in Cloudflare dashboard):
 * - GITHUB_TOKEN: Personal Access Token with 'repo' scope
 * - GITHUB_OWNER: Repository owner (username or org)
 * - GITHUB_REPO: Repository name
 * - ALLOWED_ORIGIN: Your GitHub Pages URL (for CORS)
 */

const VALID_AMINO_ACIDS = new Set('ACDEFGHIKLMNPQRSTVWY');
const MIN_LENGTH = 10;
const MAX_LENGTH = 5000;

// CORS headers
function corsHeaders(origin, allowedOrigin) {
  // Allow the specific origin or localhost for testing
  const allowOrigin = (origin === allowedOrigin || origin?.startsWith('http://localhost'))
    ? origin
    : allowedOrigin;

  return {
    'Access-Control-Allow-Origin': allowOrigin || '*',
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Max-Age': '86400',
  };
}

// Validate amino acid sequence
function validateSequence(seq) {
  const cleaned = seq.toUpperCase().replace(/[^A-Z]/g, '');
  const invalid = [...cleaned].filter(c => !VALID_AMINO_ACIDS.has(c));

  return {
    cleaned,
    length: cleaned.length,
    valid: invalid.length === 0 && cleaned.length >= MIN_LENGTH && cleaned.length <= MAX_LENGTH,
    invalidChars: [...new Set(invalid)],
    tooShort: cleaned.length < MIN_LENGTH,
    tooLong: cleaned.length > MAX_LENGTH
  };
}

// Validate ID (participant_id or sequence_name)
function validateId(id) {
  return typeof id === 'string' && /^[A-Za-z0-9_-]+$/.test(id) && id.length > 0 && id.length <= 100;
}

// Create GitHub Issue
async function createGitHubIssue(env, participantId, sequenceName, sequence) {
  const issueTitle = `[Submission] ${sequenceName} by ${participantId}`;
  const issueBody = `### Participant ID

${participantId}

### Sequence Name

${sequenceName}

### Amino Acid Sequence

${sequence}`;

  const response = await fetch(
    `https://api.github.com/repos/${env.GITHUB_OWNER}/${env.GITHUB_REPO}/issues`,
    {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${env.GITHUB_TOKEN}`,
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
        'User-Agent': 'Protein-Competition-Worker',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        title: issueTitle,
        body: issueBody,
        labels: ['submission']
      })
    }
  );

  if (!response.ok) {
    const error = await response.text();
    throw new Error(`GitHub API error: ${response.status} - ${error}`);
  }

  return await response.json();
}

// Main request handler
export default {
  async fetch(request, env, ctx) {
    const origin = request.headers.get('Origin');
    const headers = corsHeaders(origin, env.ALLOWED_ORIGIN);

    // Handle CORS preflight
    if (request.method === 'OPTIONS') {
      return new Response(null, { status: 204, headers });
    }

    // Only accept POST
    if (request.method !== 'POST') {
      return new Response(
        JSON.stringify({ success: false, error: 'Method not allowed' }),
        { status: 405, headers: { ...headers, 'Content-Type': 'application/json' } }
      );
    }

    try {
      // Parse request body
      const body = await request.json();
      const { participant_id, sequence_name, sequence } = body;

      // Validate participant_id
      if (!validateId(participant_id)) {
        return new Response(
          JSON.stringify({
            success: false,
            error: 'Invalid participant ID. Use only letters, numbers, underscores, and hyphens.'
          }),
          { status: 400, headers: { ...headers, 'Content-Type': 'application/json' } }
        );
      }

      // Validate sequence_name
      if (!validateId(sequence_name)) {
        return new Response(
          JSON.stringify({
            success: false,
            error: 'Invalid sequence name. Use only letters, numbers, underscores, and hyphens.'
          }),
          { status: 400, headers: { ...headers, 'Content-Type': 'application/json' } }
        );
      }

      // Validate sequence
      const seqResult = validateSequence(sequence || '');
      if (!seqResult.valid) {
        let errorMsg = 'Invalid sequence.';
        if (seqResult.invalidChars.length > 0) {
          errorMsg = `Invalid amino acids: ${seqResult.invalidChars.join(', ')}`;
        } else if (seqResult.tooShort) {
          errorMsg = `Sequence too short. Minimum ${MIN_LENGTH} residues required.`;
        } else if (seqResult.tooLong) {
          errorMsg = `Sequence too long. Maximum ${MAX_LENGTH} residues allowed.`;
        }
        return new Response(
          JSON.stringify({ success: false, error: errorMsg }),
          { status: 400, headers: { ...headers, 'Content-Type': 'application/json' } }
        );
      }

      // Create GitHub issue
      const issue = await createGitHubIssue(env, participant_id, sequence_name, seqResult.cleaned);

      return new Response(
        JSON.stringify({
          success: true,
          message: 'Submission received! Your sequence will be processed shortly.',
          issue_number: issue.number,
          issue_url: issue.html_url
        }),
        { status: 200, headers: { ...headers, 'Content-Type': 'application/json' } }
      );

    } catch (error) {
      console.error('Error processing submission:', error);

      return new Response(
        JSON.stringify({
          success: false,
          error: 'Failed to process submission. Please try again later.'
        }),
        { status: 500, headers: { ...headers, 'Content-Type': 'application/json' } }
      );
    }
  }
};
