# JARVIS — Türkçe Windows ve Chrome Asistanı

Windows 10/11 bilgisayarda Türkçe yazılı ve sesli komutlarla çalışan yerel kişisel asistan. Bu proje görsel bir demo değildir: Windows araçlarını yerel ajan üzerinden çalıştırır, Chrome sayfalarını eklentiyle DOM üzerinden yönetir ve yapılan işlemlerin sonucunu doğrulamaya çalışır.

> Durum: v0.2 Windows paketi otomatik testlerden ve EXE derlemesinden geçti. Gerçek Windows/Chrome uçtan uca testi kullanıcı bilgisayarında bekliyor.

## Mimari

- **JARVIS.exe:** Futuristik dashboard ve yalnızca `127.0.0.1:8765` adresine bağlanan yerel Windows ajanı.
- **JARVIS-Orb.exe:** Masaüstünde her zaman üstte kalabilen canlı mini orb.
- **Chrome eklentisi:** Sekmeler ve gerçek sayfa öğeleriyle DOM üzerinden haberleşir.
- **faster-whisper:** Türkçe konuşmayı bilgisayarda yazıya çevirir.
- **Ollama:** İsteğe bağlı, ücretsiz ve yerel doğal komut yorumlama.
- **SQLite:** Görev geçmişini yalnızca yerel bilgisayarda tutar.

## Uygulanan güvenlik kuralları

- Sunucu sadece localhost üzerinde dinler; uzaktan kontrol portu açmaz.
- Model sınırsız PowerShell veya terminal çalıştıramaz. Yalnızca tanımlı araçlar çağrılabilir.
- Dosya erişimi varsayılan olarak Masaüstü, Belgeler ve İndirilenler ile sınırlıdır.
- Taşıma/yeniden adlandırma ve zorla kapatma işlemleri onay ister.
- Silme kalıcı yapılmaz; Geri Dönüşüm Kutusu'na gönderilir ve `ONAYLIYORUM` son onayı ister.
- API anahtarları koda, GitHub'a ve işlem geçmişine yazılmaz.
- Chrome eşleştirmesi 6 haneli tek kullanımlık kod ve cihazda saklanan uzun rastgele anahtar kullanır.
- CAPTCHA, iki aşamalı doğrulama ve Chrome'un özel sayfaları otomatik aşılmaz.

## Çalışan temel komut örnekleri

- `Chrome'u aç`
- `YouTube'u aç`
- `Google'da PUBG Mobile güncellemesini ara`
- `Açık sekmeleri say`
- `Bu sayfayı oku` / `Bu sayfayı özetle`
- `Bu sayfada LDPlayer yazan yeri bul`
- `İkinci sonuca gir`
- `Bir önceki sekmeye dön` / `Bu sekmeyi kapat`
- `Sayfayı aşağı kaydır`
- `Yayınla butonuna bas` (onay ister)
- `Videoyu durdur`
- `Ses seviyesini yüzde 30 yap`
- `RAM ve işlemci kullanımını söyle`
- `Ekran görüntüsü al`
- `Masaüstünde Jarvis Test klasörü oluştur`
- `Not Defteri'ni aç ve deneme yaz`
- `Dur` / `İptal` / `Sus`

## Hazır Windows paketini kurma

1. GitHub **Actions → Windows paketi** sayfasındaki son başarılı çalışmayı açın.
2. **Artifacts** bölümünden `JARVIS-Yilmaz-Windows` paketini indirin.
3. ZIP dosyasını tamamen çıkarın.
4. `KURULUM.bat` dosyasına çift tıklayın.
5. Kurulum bitince masaüstündeki **JARVIS** kısayolunu açın.

İlk sesli komutta Whisper `small` modeli indirileceği için bir defaya mahsus bekleme olabilir.

## Chrome eklentisini bağlama

1. Chrome adres çubuğuna `chrome://extensions` yazın.
2. Sağ üstten **Geliştirici modu** seçeneğini açın.
3. **Paketlenmemiş öğe yükle** düğmesine basın.
4. Kurulum dizinindeki `chrome-extension` klasörünü seçin.
5. JARVIS → Ayarlar ekranındaki 6 haneli kodu eklentinin Ayarlar sayfasına girin.
6. Dashboard'da Chrome durumu **Bağlı** olmalıdır.

## Ücretsiz Türkçe ses

JARVIS, Windows/Edge WebView içinde kurulu Türkçe sistem seslerini ücretsiz ve API anahtarı olmadan kullanır. JARVIS → Ayarlar bölümünde algılanan Türkçe sesi seçebilirsiniz.

Türkçe ses listede görünmüyorsa Windows 10'da **Ayarlar → Saat ve Dil → Konuşma → Sesleri yönet → Ses ekle → Türkçe** yoluyla Microsoft'un Türkçe ses paketini kurun. Mikrofon metni ilk kullanımda indirilen yerel faster-whisper modeliyle cihazda çözümlenir; ham kayıt işlem bitince silinir.

## Ücretsiz yerel AI

[Ollama](https://ollama.com/download/windows) kurulduktan sonra:

```powershell
ollama pull qwen3:4b
```

JARVIS Ollama'yı `127.0.0.1:11434` üzerinden otomatik algılar. Ollama yoksa açık ve güvenli temel komutlar kural tabanlı olarak çalışmaya devam eder.

## OpenAI API hakkında

ChatGPT Plus üyeliği ile OpenAI API bakiyesi aynı şey değildir. API kullanılacaksa kullanıcı kendi API anahtarını **JARVIS → Ayarlar → OpenAI API** bölümüne yerel olarak girer. Anahtar Windows Kimlik Bilgisi Yöneticisi'nde saklanır ve hiçbir zaman GitHub'a ya da görev geçmişine yazılmaz.

OpenAI planlayıcı varsayılan olarak kapalıdır. Kullanıcı isterse yalnızca hassas olmayan komutları veya tüm komut metinlerini API'ye gönderme kapsamını açıkça seçer. Tanınan temel komutlar önce cihazda ayrıştırılır; parola, kart, token ve benzeri hassas ifadeler “hassas olmayan” modda buluta gönderilmez. **Bağlantıyı test et** düğmesi küçük bir API isteğiyle anahtar/model/bakiye durumunu doğrular.

## Kaynak koddan çalıştırma

Python 3.11 kurulu Windows bilgisayarda:

```powershell
git clone https://github.com/djsimal08/jarvis-yilmaz.git
cd jarvis-yilmaz
git switch main
.\KURULUM.bat
```

## Doğrulama durumu

| Test | Otomatik test | Gerçek Windows testi |
|---|---:|---:|
| Güvenlik/risk sınıflandırması | Var | Bekliyor |
| Türkçe temel komut ayrıştırma | Var | Bekliyor |
| Python sözdizimi | Var | — |
| Windows EXE oluşturma | GitHub Actions | Başarılı (v0.2) |
| Uygulama/pencere/ses kontrolü | — | Kullanıcı PC testi gerekli |
| Chrome DOM ve sekme kontrolü | — | Eklenti kurulumundan sonra gerekli |
| Türkçe mikrofon | — | İlk model indirmesinden sonra gerekli |

Gerçek Windows ve Chrome testleri tamamlanmadan proje “tamamlandı” olarak etiketlenmez.
