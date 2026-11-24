"""Fixed clinical profiles for the 20 simulated patients."""

PATIENTS: list[dict] = [
    {"id":"patient_001","name":"Ana Souza","age":34,"bed":"UTI-01","profile":"healthy","baseline":{"hr":(68,78),"spo2":(97,100),"sbp":(115,125),"dbp":(75,82)}},
    {"id":"patient_002","name":"Carlos Lima","age":46,"bed":"UTI-02","profile":"healthy","baseline":{"hr":(60,75),"spo2":(97,100),"sbp":(110,120),"dbp":(70,78)}},
    {"id":"patient_003","name":"Mariana Alves","age":29,"bed":"UTI-03","profile":"healthy","baseline":{"hr":(65,80),"spo2":(97,100),"sbp":(112,125),"dbp":(72,82)}},
    {"id":"patient_004","name":"João Pedro Carvalho","age":52,"bed":"UTI-04","profile":"healthy","baseline":{"hr":(62,76),"spo2":(97,100),"sbp":(115,122),"dbp":(74,80)}},
    {"id":"patient_005","name":"Beatriz Rocha","age":41,"bed":"UTI-05","profile":"healthy","baseline":{"hr":(68,79),"spo2":(97,100),"sbp":(114,124),"dbp":(71,81)}},
    {"id":"patient_006","name":"Rafael Costa","age":38,"bed":"ENF-01","profile":"healthy","baseline":{"hr":(64,78),"spo2":(97,100),"sbp":(110,123),"dbp":(70,79)}},
    {"id":"patient_007","name":"Luciana Dias","age":57,"bed":"ENF-02","profile":"healthy","baseline":{"hr":(66,80),"spo2":(97,100),"sbp":(116,125),"dbp":(73,82)}},
    {"id":"patient_008","name":"Gabriel Moraes","age":25,"bed":"ENF-03","profile":"healthy","baseline":{"hr":(60,74),"spo2":(97,100),"sbp":(112,120),"dbp":(70,77)}},
    {"id":"patient_009","name":"Fernanda Ribeiro","age":63,"bed":"UTI-06","profile":"hypertensive","baseline":{"hr":(70,90),"spo2":(96,99),"sbp":(125,138),"dbp":(80,88)}},
    {"id":"patient_010","name":"Paulo Martins","age":71,"bed":"UTI-07","profile":"hypertensive","baseline":{"hr":(72,88),"spo2":(96,99),"sbp":(125,138),"dbp":(82,88)}},
    {"id":"patient_011","name":"Helena Cardoso","age":58,"bed":"ENF-04","profile":"hypertensive","baseline":{"hr":(70,86),"spo2":(96,99),"sbp":(125,138),"dbp":(80,88)}},
    {"id":"patient_012","name":"Roberto Nunes","age":67,"bed":"ENF-05","profile":"hypertensive","baseline":{"hr":(75,90),"spo2":(96,99),"sbp":(125,138),"dbp":(80,89)}},
    {"id":"patient_013","name":"Camila Teixeira","age":32,"bed":"UTI-08","profile":"tachycardic","baseline":{"hr":(85,98),"spo2":(96,99),"sbp":(120,135),"dbp":(78,88)}},
    {"id":"patient_014","name":"Diego Fernandes","age":44,"bed":"ENF-06","profile":"tachycardic","baseline":{"hr":(85,98),"spo2":(96,99),"sbp":(122,135),"dbp":(80,88)}},
    {"id":"patient_015","name":"Patrícia Gomes","age":36,"bed":"ENF-07","profile":"tachycardic","baseline":{"hr":(85,98),"spo2":(96,99),"sbp":(121,135),"dbp":(78,86)}},
    {"id":"patient_016","name":"Antônio Vieira","age":76,"bed":"UTI-09","profile":"bradycardic","baseline":{"hr":(55,70),"spo2":(96,99),"sbp":(100,115),"dbp":(62,72)}},
    {"id":"patient_017","name":"Sônia Azevedo","age":69,"bed":"ENF-08","profile":"bradycardic","baseline":{"hr":(55,70),"spo2":(96,99),"sbp":(102,115),"dbp":(64,72)}},
    {"id":"patient_018","name":"Eduardo Barros","age":61,"bed":"UTI-10","profile":"critical","baseline":{"hr":(85,100),"spo2":(95,99),"sbp":(125,140),"dbp":(80,90)}},
    {"id":"patient_019","name":"Juliana Freitas","age":55,"bed":"ENF-09","profile":"critical","baseline":{"hr":(85,100),"spo2":(95,99),"sbp":(125,140),"dbp":(80,90)}},
    {"id":"patient_020","name":"Lucas Santana","age":48,"bed":"ENF-10","profile":"recovering","baseline":{"hr":(75,90),"spo2":(97,100),"sbp":(125,135),"dbp":(80,88)}},
]
