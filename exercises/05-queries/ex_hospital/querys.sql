USE hospital;

-- 1. Lista todos os casos de cada paciente, com o nome do paciente e do caso.
--    Útil para ver o historial clínico completo de um paciente.
SELECT p.id AS patient_id,
       p.name AS patient_name,
       c.id AS case_id,
       c.name AS case_name
FROM Patients p
JOIN Cases c ON c.patient_id = p.id
ORDER BY p.name, c.id;

-- 2. Calcula o custo total faturado por cada paciente (soma de todas as
--    finanças dos seus casos), do mais caro para o mais barato.
--    Útil para a área financeira identificar os pacientes com maior faturação.
SELECT p.id,
       p.name,
       SUM(f.cost) AS total_cost
FROM Patients p
JOIN Cases c ON c.patient_id = p.id
JOIN Finances f ON f.case_id = c.id
GROUP BY p.id, p.name
ORDER BY total_cost DESC;

-- 3. Mostra o horário (turnos) de cada funcionário, com a unidade onde
--    trabalha, apenas para os turnos de hoje em diante.
--    Útil para planear a escala e saber quem está em cada unidade.
SELECT s.name AS staff_name,
       u.name AS unit_name,
       sh.name AS shift_name,
       sh.start_time,
       sh.end_time
FROM Shift sh
JOIN Staffs s ON s.id = sh.staff_id
JOIN Units u ON u.id = sh.unit_id
WHERE sh.start_time >= CURDATE()
ORDER BY sh.start_time;

-- 4. Conta quantos episódios cada funcionário acompanha e devolve só os
--    que acompanham mais de 3. Útil para detetar sobrecarga de trabalho.
SELECT Staffs.id,
       Staffs.name,
       COUNT(Episodes_Staffs.episode_id) AS total_episodes
FROM Staffs
JOIN Episodes_Staffs ON Episodes_Staffs.staff_id = Staffs.id
GROUP BY Staffs.id, Staffs.name
HAVING COUNT(Episodes_Staffs.episode_id) > 3
ORDER BY total_episodes DESC;

-- 5. Lista os casos que têm seguro associado, mostrando o paciente, o nome
--    do seguro e o custo da fatura. Útil para saber que despesas são
--    cobertas por seguradoras e quais ficam a cargo do paciente.
SELECT p.name AS patient_name,
       c.name AS case_name,
       i.name AS insurance_name,
       f.cost,
       f.createdAt
FROM Finances f
JOIN Finance_Insurance fi ON fi.finance_id = f.id
JOIN Insurances i ON i.id = fi.insurance_id
JOIN Cases c ON c.id = f.case_id
JOIN Patients p ON p.id = c.patient_id
ORDER BY f.createdAt DESC;