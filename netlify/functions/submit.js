/**
 * Netlify Function for Protein Competition Submissions
 *
 * Receives form submissions and creates GitHub Issues.
 *
 * Environment variables (set in Netlify dashboard):
 * - GITHUB_TOKEN: Personal Access Token with 'repo' scope
 * - GITHUB_OWNER: Repository owner (seoklab)
 * - GITHUB_REPO: Repository name (design-test)
 */

const VALID_AMINO_ACIDS = new Set('ACDEFGHIKLMNPQRSTVWY');
const MIN_LENGTH = 10;
const MAX_LENGTH = 5000;

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

function validateId(id) {
  return typeof id === 'string' && /^[A-Za-z0-9_-]+$/.test(id) && id.length > 0 && id.length <= 100;
}

async function createGitHubIssue(participantId, email, sequenceName, sequence) {
  const issueTitle = `[Submission] ${sequenceName} by ${participantId}`;
  const issueBody = `### Participant ID

${participantId}

### Email

${email}

### Sequence Name

${sequenceName}

### Amino Acid Sequence

${sequence}`;

  const response = await fetch(
    `https://api.github.com/repos/${process.env.GITHUB_OWNER}/${process.env.GITHUB_REPO}/issues`,
    {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${process.env.GITHUB_TOKEN}`,
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
        'User-Agent': 'Protein-Competition-Netlify',
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

exports.handler = async (event, context) => {
  // CORS headers
  const headers = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
    'Content-Type': 'application/json'
  };

  // Handle CORS preflight
  if (event.httpMethod === 'OPTIONS') {
    return { statusCode: 204, headers, body: '' };
  }

  // Only accept POST
  if (event.httpMethod !== 'POST') {
    return {
      statusCode: 405,
      headers,
      body: JSON.stringify({ success: false, error: 'Method not allowed' })
    };
  }

  try {
    const body = JSON.parse(event.body);
    const { participant_id, email, sequence_name, sequence } = body;

    // Validate participant_id
    if (!validateId(participant_id)) {
      return {
        statusCode: 400,
        headers,
        body: JSON.stringify({
          success: false,
          error: 'Invalid participant ID. Use only letters, numbers, underscores, and hyphens.'
        })
      };
    }

    // Validate email
    if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      return {
        statusCode: 400,
        headers,
        body: JSON.stringify({
          success: false,
          error: 'Please provide a valid email address.'
        })
      };
    }

    // Validate sequence_name
    if (!validateId(sequence_name)) {
      return {
        statusCode: 400,
        headers,
        body: JSON.stringify({
          success: false,
          error: 'Invalid sequence name. Use only letters, numbers, underscores, and hyphens.'
        })
      };
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
      return {
        statusCode: 400,
        headers,
        body: JSON.stringify({ success: false, error: errorMsg })
      };
    }

    // Create GitHub issue
    const issue = await createGitHubIssue(participant_id, email, sequence_name, seqResult.cleaned);

    return {
      statusCode: 200,
      headers,
      body: JSON.stringify({
        success: true,
        message: 'Submission received! Your sequence will be processed shortly.',
        issue_number: issue.number,
        issue_url: issue.html_url
      })
    };

  } catch (error) {
    console.error('Error processing submission:', error);
    return {
      statusCode: 500,
      headers,
      body: JSON.stringify({
        success: false,
        error: 'Failed to process submission. Please try again later.'
      })
    };
  }
};
