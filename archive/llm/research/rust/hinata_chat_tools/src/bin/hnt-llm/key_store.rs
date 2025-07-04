use crate::{DeleteKey, ListKeys, SaveKey, PROVIDERS};
use anyhow::{Context, Result};
use base64::{engine::general_purpose, Engine as _};
use rand::RngCore;
use std::path::{Path, PathBuf};
use tokio::fs;

/// Handles the 'save-key' subcommand.
pub async fn handle_save_key(args: &SaveKey) -> Result<()> {
    let canonical_name = match PROVIDERS.iter().find(|p| {
        p.name.eq_ignore_ascii_case(&args.name) || p.env_var.eq_ignore_ascii_case(&args.name)
    }) {
        Some(p) => p.name,
        None => &args.name,
    };

    let config_dir = get_hinata_dir("config").await?;
    let data_dir = get_hinata_dir("data").await?;
    ensure_local_key(&data_dir).await?;

    let keys_path = config_dir.join("keys");

    let api_key = rpassword::prompt_password(format!("Enter API key for '{}': ", canonical_name))
        .with_context(|| "Failed to read API key from prompt")?;

    let mut lines = if fs::try_exists(&keys_path).await? {
        fs::read_to_string(&keys_path)
            .await?
            .lines()
            .map(String::from)
            .collect()
    } else {
        Vec::new()
    };

    let key_prefix = format!("{}=", canonical_name);
    let key_exists = lines.iter().any(|line| line.starts_with(&key_prefix));
    lines.retain(|line| !line.starts_with(&key_prefix));

    let local_key = read_local_key(&data_dir).await?;
    let mut data_to_encrypt = api_key.into_bytes();
    xor_crypt(&local_key, &mut data_to_encrypt);

    let encoded_key = general_purpose::STANDARD.encode(&data_to_encrypt);
    lines.push(format!("{}={}", canonical_name, encoded_key));

    fs::write(&keys_path, lines.join("\n") + "\n").await?;
    set_permissions(&keys_path).await?;

    if key_exists {
        println!("Updated key '{}'.", canonical_name);
    } else {
        println!("Saved key '{}'.", canonical_name);
    }

    Ok(())
}

/// Handles the 'list-keys' subcommand.
pub async fn handle_list_keys(_args: &ListKeys) -> Result<()> {
    let config_dir = get_hinata_dir("config").await?;
    let keys_path = config_dir.join("keys");

    if !fs::try_exists(&keys_path).await? {
        println!("No keys saved.");
        return Ok(());
    }

    let content = fs::read_to_string(keys_path).await?;
    let keys: Vec<_> = content
        .lines()
        .filter(|line| !line.is_empty())
        .filter_map(|line| line.split('=').next())
        .collect();

    if keys.is_empty() {
        println!("No keys saved.");
    } else {
        println!("Saved API keys:");
        for key in keys {
            println!("- {}", key);
        }
    }

    Ok(())
}

/// Handles the 'delete-key' subcommand.
pub async fn handle_delete_key(args: &DeleteKey) -> Result<()> {
    let config_dir = get_hinata_dir("config").await?;
    let keys_path = config_dir.join("keys");

    if !fs::try_exists(&keys_path).await? {
        println!("Key '{}' not found.", args.name);
        return Ok(());
    }

    let lines: Vec<String> = fs::read_to_string(&keys_path)
        .await?
        .lines()
        .map(String::from)
        .collect();

    let key_prefix = format!("{}=", args.name);
    let mut key_found = false;
    let new_lines: Vec<_> = lines
        .into_iter()
        .filter(|line| {
            if line.starts_with(&key_prefix) {
                key_found = true;
                false
            } else {
                true
            }
        })
        .collect();

    if !key_found {
        println!("Key '{}' not found.", args.name);
        return Ok(());
    }

    fs::write(&keys_path, new_lines.join("\n") + "\n").await?;
    set_permissions(&keys_path).await?;

    println!("Deleted key '{}'.", args.name);

    Ok(())
}

pub async fn get_api_key_from_store(key_name: &str) -> anyhow::Result<Option<String>> {
    let config_dir = get_hinata_dir("config").await?;
    let keys_path = config_dir.join("keys");

    if !fs::try_exists(&keys_path).await? {
        return Ok(None);
    }

    let content = fs::read_to_string(&keys_path).await?;
    let key_prefix = format!("{}=", key_name);

    if let Some(line) = content.lines().find(|line| line.starts_with(&key_prefix)) {
        if let Some(encoded_key) = line.split_once('=').map(|x| x.1) {
            let data_dir = get_hinata_dir("data").await?;
            let local_key = read_local_key(&data_dir).await?;
            let mut encrypted_data = general_purpose::STANDARD.decode(encoded_key)?;
            xor_crypt(&local_key, &mut encrypted_data);
            let api_key = String::from_utf8(encrypted_data)?;
            return Ok(Some(api_key));
        }
    }

    Ok(None)
}

async fn get_hinata_dir(dir_type: &str) -> anyhow::Result<PathBuf> {
    let base_dir = match dir_type {
        "config" => dirs::config_dir(),
        "data" => dirs::data_dir(),
        _ => {
            return Err(anyhow::anyhow!(
                "Invalid directory type specified: '{}'",
                dir_type
            ))
        }
    };

    let dir = base_dir
        .ok_or_else(|| anyhow::anyhow!("Could not find {} directory", dir_type))?
        .join("hinata");

    fs::create_dir_all(&dir)
        .await
        .with_context(|| format!("Failed to create directory at {}", dir.display()))?;
    Ok(dir)
}

async fn ensure_local_key(data_dir: &Path) -> anyhow::Result<()> {
    let key_path = data_dir.join(".local_key");
    if !fs::try_exists(&key_path).await? {
        let mut key = [0u8; 32];
        rand::thread_rng().fill_bytes(&mut key);
        fs::write(&key_path, key)
            .await
            .with_context(|| "Failed to write local key")?;
        set_permissions(&key_path).await?;
    }
    Ok(())
}

async fn read_local_key(data_dir: &Path) -> anyhow::Result<Vec<u8>> {
    let key_path = data_dir.join(".local_key");
    fs::read(&key_path)
        .await
        .with_context(|| "Failed to read local key")
}

fn xor_crypt(key: &[u8], data: &mut [u8]) {
    for (i, byte) in data.iter_mut().enumerate() {
        *byte ^= key[i % key.len()];
    }
}

async fn set_permissions(path: &Path) -> anyhow::Result<()> {
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let perms = std::fs::Permissions::from_mode(0o600);
        fs::set_permissions(path, perms)
            .await
            .with_context(|| format!("Failed to set permissions on {}", path.display()))?;
    }
    // On non-UNIX systems, this is a no-op.
    Ok(())
}
